import json
import io
import logging
import math
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

import pandas as pd
import requests
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobClient
from langchain_core.documents import Document
from langchain_community.vectorstores.azuresearch import AzureSearch
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_text_splitters.markdown import RecursiveCharacterTextSplitter
from openai import AzureOpenAI
from pydantic import BaseModel, Field
from azure.search.documents.indexes.models import SearchField, SearchFieldDataType, SimpleField


from .config import load_settings, Settings


logger = logging.getLogger(__name__)
settings = load_settings()

index_fields = [
    SimpleField (
        name = "id",
        type = SearchFieldDataType.String,
        key = True,
        filterable = True
    ),
    SimpleField (
        name = "content", # <-- question
        type = SearchFieldDataType.String,
    ),
    SearchField (
        name = "content_vector", # <-- question vector
        type = SearchFieldDataType.Collection(SearchFieldDataType.Single),
        searchable = True,
        vector_search_dimensions = 3072,
        vector_search_profile_name = settings.vector_search_profile_name,
    ),
    SimpleField (
        name = "document_title", # <-- field to filter by document_title
        type = SearchFieldDataType.String,
        filterable = True
    ),
    SimpleField (
        name = "chatbot", # <-- field to filter by chatbot
        type = SearchFieldDataType.String,
        filterable = True
    ),
    SimpleField (
        name= "metadata", # <-- document_title, document_chunk, page_number, chatbot
        type = SearchFieldDataType.String
    )
]
qna_fields = [
    SimpleField (
        name = "id",
        type = SearchFieldDataType.String,
        key = True,
        filterable = True
    ),
    SimpleField (
        name = "content", # <-- question
        type = SearchFieldDataType.String,
    ),
    SearchField (
        name = "content_vector", # <-- question vector
        type = SearchFieldDataType.Collection(SearchFieldDataType.Single),
        searchable = True,
        vector_search_dimensions = 3072,
        vector_search_profile_name = settings.vector_search_profile_name,
    ),
    SimpleField (
        name = "qna_filename", # <-- field to filter by qna_filename
        type = SearchFieldDataType.String,
        filterable = True
    ),
    SimpleField (
        name = "chatbot", # <-- field to filter by chatbot
        type = SearchFieldDataType.String,
        filterable = True
    ),
    SimpleField (
        name= "metadata", # <-- document_title, expected_answer, page_number, chatbot
        type = SearchFieldDataType.String
    )
]



class ChunkQuestions(BaseModel):
    question1: str = Field(description="A general question covering the main idea, topic, or purpose of the content. If the input is already a question, preserve it here.")
    question2: str = Field(description="A question probing deeper into specific details, implications, or data points found within the content.")
    question3: str = Field(description="A question addressing applications, consequences, or relationships between different elements in the content.")


def _log_step_start(step_name: str, **fields) -> float:
    field_str = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    logger.info("[STEP_START] %s %s", step_name, field_str)
    return perf_counter()


def _log_step_done(step_name: str, started_at: float, **fields) -> None:
    elapsed_ms = (perf_counter() - started_at) * 1000
    field_str = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    logger.info("[STEP_DONE] %s elapsed_ms=%.2f %s", step_name, elapsed_ms, field_str)


def _safe_len(value) -> int:
    return len(value) if value is not None else 0


class IngestionRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.doc_int_client = DocumentIntelligenceClient(
            endpoint=settings.doc_int_endpoint,
            credential=AzureKeyCredential(settings.doc_int_key),
        )
        self.openai_client = AzureOpenAI(
            api_key=settings.aoai_key,
            azure_endpoint=settings.aoai_endpoint,
            api_version=settings.ingest_model_api_version,
        )
        self.llm_fixer = AzureChatOpenAI(
            openai_api_version=settings.ingest_model_api_version,
            azure_deployment=settings.ingest_model_name,
            api_key=settings.aoai_key,
            temperature=settings.deterministic_tmp,
            azure_endpoint=settings.aoai_endpoint,
        )
        self.llm_generator = AzureChatOpenAI(
            openai_api_version=settings.ingest_model_api_version,
            azure_deployment=settings.ingest_model_name,
            api_key=settings.aoai_key,
            temperature=settings.creative_tmp,
            azure_endpoint=settings.aoai_endpoint,
        )
        self.embedding_client = AzureOpenAIEmbeddings(
            model=settings.embedding_model_name,
            openai_api_version=settings.embedding_model_api_version,
            openai_api_key=settings.aoai_key,
            azure_endpoint=settings.aoai_endpoint,
        )
        # Use the same AzureSearch client pattern as app-side ingestion.
        self.kb_search = AzureSearch(
            azure_search_endpoint=settings.ai_search_endpoint,
            azure_search_key=settings.ai_search_key,
            index_name=settings.index_name,
            embedding_function=self.embedding_client,
            fields=index_fields,
        )
        self.qna_search = AzureSearch(
            azure_search_endpoint=settings.ai_search_endpoint,
            azure_search_key=settings.ai_search_key,
            index_name=settings.qna_index_name,
            embedding_function=self.embedding_client,
            fields=qna_fields,
        )

    def chat_completion(self, prompt: str, temperature: float) -> str:
        resp = self.openai_client.chat.completions.create(
            model=self.settings.ingest_model_name,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return (resp.choices[0].message.content or "").strip()

    def embedding(self, text: str) -> list[float]:
        resp = self.openai_client.embeddings.create(
            model=self.settings.embedding_model_name,
            input=text,
        )
        return resp.data[0].embedding


class DocumentIngestor:
    def __init__(self, runtime: IngestionRuntime, chatbot_id: str, chatbot_name: str, document_title: str, document_path: str):
        self.runtime = runtime
        self.settings = runtime.settings
        self.chatbot_id = chatbot_id
        self.chatbot_name = chatbot_name
        self.document_title = document_title
        self.document_path = document_path
        self.document_type = document_title.split(".")[-1].lower()

        self.page_re = re.compile(r'<!-- PageNumber="(\d+)" -->')
        self.page_break = "<!-- PageBreak -->"

    def _filter_value(self) -> str:
        # Keep ingestion filter key consistent with app retrievers.
        return self.chatbot_id

    def get_file_from_blob_storage(self) -> bytes:
        blob_client = BlobClient(
            account_url=self.settings.storage_url,
            container_name=self.settings.container_name,
            credential=self.settings.storage_key,
            blob_name=self.document_path,
        )
        return blob_client.download_blob().readall()

    def convert_docx_to_pdf_bytes(self, docx_bytes: bytes) -> bytes:
        files = {
            "file": (
                self.document_title,
                io.BytesIO(docx_bytes),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        }
        try:
            response = requests.post(self.settings.docx_to_pdf_api_url, files=files, timeout=self.settings.timeout)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException:
            return None

    def extract_from_doc_bytes(self, file_bytes: bytes) -> AnalyzeResult:
        try:
            poller = self.runtime.doc_int_client.begin_analyze_document(
                "prebuilt-layout",
                body=file_bytes,
                output_content_format="markdown",
            )
            return poller.result()
        except Exception:
            return None

    def reconstruct_page_numbers(self, text: str) -> str:
        if self.page_break in text:
            pages = text.split(self.page_break)
            rebuilt = []
            for i, page_content in enumerate(pages):
                page_num = i + 1
                page_content = self.page_re.sub("\n", page_content).strip()
                rebuilt.append(f'\n<!-- PageNumber="{page_num}" -->\n{page_content}\n')
            return self.page_break.join(rebuilt)

        page_size = 3000
        segments = []
        for i in range(0, len(text), page_size):
            page_num = (i // page_size) + 1
            segment = text[i : i + page_size]
            segments.append(f'<!-- PageNumber="{page_num}" -->\n{segment}')
        return "\n".join(segments)

    def enhance_extraction_result(self, result: AnalyzeResult) -> str:
        lcontent = result.content.split(self.page_break)

        def _enhance_one(content: str) -> str:
            enhance_extraction_prompt = f"""
            **Role**:
            You are an expert text reformater. Given a text representing a document, extract with the *highest fidelity*
            the text contained within, reformatting them to improve readability and coherence. You MAY NOT OMIT any texts of the input.

            **CRITICAL INSTRUCTION**:
            The input text contains structural page markers: `<!-- PageNumber="n" -->`.
            - You MUST PRESERVE these markers EXACTLY as they are in the output (e.g., `<!-- PageNumber="1" -->`).
            - They MUST sit on their own line at the very beginning of each page's content.
            - DO NOT add `> `, `#`, or any other prefix/formatting to these tags.
            - Each marker represents the start of a new page. DO NOT delete, modify, translate, or move these markers.

            **Input**:
            The text input contains extracted raw text, but certain paragraphs and text has lost their structure (tables, bullet points, diagrams, OCR from figures, etc.).

            **Goal**:
            Your role is to reformat the raw text from documents into a more structured Markdown text, by detecting the intent and semantic meaning of the paragraph
            to ensure a more coherent document. You MUST keep the text in the output, but restructure them into tables or bullet points.

            **Instructions**:
            Follow these steps:
                - Examine the text carefully, identify the meaning and intent of each paragraph.
                - Identify all elements present in the page, including headers, body text, footnotes, tables, captions, and page numbers, etc.
                - Extract all raw text and format them according to the *Output format*, while respecting the reading order.
                - You MUST maintain the EXACT position and format of all `<!-- PageNumber="..." -->` tags found in the input. Ensure they remain on their own line WITHOUT any markdown prefix.
                - For any unstructured text that is floating or breaks the normal reading pattern of the document, reformat them into structured content:
                    - either a table, or bullet points.

            **Output format**:
                - Return ONLY the reformatted text as is.
                - For layout elements (headers and footers), you must use:
                    - '> ' before every page header and page footer.
                    - '# ' before every title.
                    - '## ' before every section heading.
                    - '### ' before every subsection, etc..
                - For text extracted from tables:
                    - format the output as a HTML table.
                - For lists, use:
                    - * or - for bulleted, 1. 2. 3. for numbered.
                - For bold or italics words and sentences:
                    - bold: wrap the text with **.
                    - italics: wrap the text with *.

            **Example**:
            <!-- PageNumber="1" -->
            > page header: es tu, brute

            # Document Title

            ## 1. Section Heading XYZ
            ...
            ---
            Here is the input text:
            {content}
            """
            resp = self.runtime.llm_fixer.invoke(enhance_extraction_prompt)
            return resp.content

        with ThreadPoolExecutor(max_workers=self.settings.ingest_max_workers) as executor:
            lenhanced = list(executor.map(_enhance_one, lcontent))

        return "\n".join(lenhanced)

    def chunk_markdown(self, text: str) -> list[Document]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )
        chunks = splitter.split_documents([Document(page_content=text)])
        return self.attach_page_metadata(chunks)

    def attach_page_metadata(self, chunks: list[Document]) -> list[Document]:
        current_page = 0
        for chunk in chunks:
            found_pages = sorted({int(p) for p in self.page_re.findall(chunk.page_content)})
            if found_pages:
                chunk.metadata["page_number"] = [found_pages[0] - 1] + found_pages if current_page else found_pages
                current_page = found_pages[-1]
            else:
                chunk.metadata["page_number"] = [current_page]
            chunk.page_content = self.page_re.sub("", chunk.page_content).strip()
        return chunks

    def _generate_questions(self, chunk_text: str) -> tuple[str, str, str]:
        prompt = (
            "Generate 3 standalone user questions from this text. "
            "Return strict JSON object with keys question1, question2, question3.\n\nInput:\n"
            f"{chunk_text}"
        )
        raw = self.runtime.chat_completion(prompt, temperature=1)
        try:
            obj = json.loads(raw)
            return obj["question1"], obj["question2"], obj["question3"]
        except Exception:
            return (
                chunk_text[:120] or "What is the main topic?",
                "Can you provide more details about this topic?",
                "How can this information be applied?",
            )

    def enrich_chunks(self, chunks: list[Document]) -> list[Document]:
        filter_value = self._filter_value()
        structured_llm = self.runtime.llm_generator.with_structured_output(ChunkQuestions)
        enhanced: list[Document] = []

        for i, chunk in enumerate(chunks, start=1):
            gen_questions_prompt = f"""
            You are a versatile question-generation expert:
            - **Language**: The input may be in Vietnamese or English. Regardless of the input language, generate all questions (question1, question2, question3) in English only.
            - Treat the input as a source of knowledge, not as an object to be summarized.
            - Never refer to the input format in your questions (e.g., avoid "What does this table say" or "What is in this paragraph").
            - Never include the original source text in your output.
            - Focus on the *subject matter*, not the *document structure*.
            - Generate questions that stand alone and make sense to a user who hasn't seen the source chunk.

            Depending on the input type, your task is as follows:
            - If the input is already a question, your task is as follows:
                1. Use the original question as 'question1', translated to English if it is in Vietnamese.
                2. Generate two additional questions ('question2', 'question3') in English that probe deeper into the topic or related aspects.

            - If the input is a table, generate 3 questions that helps to find and understand the data:
                1. A question about what informations the table contains, or its purpose.
                2. A general question that could be answered using one or more rows of the table.
                3. A question addressing the relationships between columns.

            - If the input is a paragraph, generate 3 common questions that people frequenly ask about the given information:
                1. A general question covering the main idea or topic.
                2. A question probing deeper into specific details or implications.
                3. A question addressing potential applications, consequences, or related aspects.

            Please return the output in a Python dictionary format with the following keys: 'question1', 'question2', 'question3'.

            Here is the input:
            {chunk.page_content}
            """
            try:
                output_questions = structured_llm.invoke(gen_questions_prompt)
                logger.info("[Q&C PAIR] processed chunk %s/%s", i, len(chunks))
                for q_text in [output_questions.question1, output_questions.question2, output_questions.question3]:
                    enhanced.append(
                        Document(
                            page_content=q_text,
                            metadata={
                                "document_title": self.document_title,
                                "chatbot": filter_value,
                                "metadata": json.dumps(
                                    {
                                        "chatbot": filter_value,
                                        "document_title": self.document_title,
                                        "page_number": str(chunk.metadata.get("page_number")),
                                        "document_chunk": chunk.page_content,
                                    }
                                ),
                            },
                        )
                    )
            except Exception as exc:
                logger.error("[Q&C PAIR] chunk %s failed: %s", i, exc)

        return enhanced

    def enrich_and_upload_chunks(self, chunks: list[Document]) -> int:
        """Enrich chunks in parallel and upload to AI Search in batches as results arrive."""
        filter_value = self._filter_value()
        structured_llm = self.runtime.llm_generator.with_structured_output(ChunkQuestions)
        total_chunks = len(chunks)
        upload_batch_size = self.settings.ingest_upload_batch_size
        total_docs = 0
        upload_batch: list[Document] = []

        def _enrich_one(i: int, chunk: Document) -> list[Document]:
            gen_questions_prompt = f"""
            You are a versatile question-generation expert:
            - Treat the input as a source of knowledge, not as an object to be summarized.
            - Never refer to the input format in your questions (e.g., avoid "What does this table say" or "What is in this paragraph").
            - Never include the original source text in your output.
            - Focus on the *subject matter*, not the *document structure*.
            - Generate questions that stand alone and make sense to a user who hasn't seen the source chunk.

            Depending on the input type, your task is as follows:
            - If the input is already a question, your task is as follows:
                1. Preserve the original question exactly as 'question1'.
                2. Generate two additional questions ('question2', 'question3') that probe deeper into the topic or related aspects.

            - If the input is a table, generate 3 questions that helps to find and understand the data:
                1. A question about what informations the table contains, or its purpose.
                2. A general question that could be answered using one or more rows of the table.
                3. A question addressing the relationships between columns.

            - If the input is a paragraph, generate 3 common questions that people frequenly ask about the given information:
                1. A general question covering the main idea or topic.
                2. A question probing deeper into specific details or implications.
                3. A question addressing potential applications, consequences, or related aspects.

            Please return the output in a Python dictionary format with the following keys: 'question1', 'question2', 'question3'.

            Here is the input:
            {chunk.page_content}
            """
            try:
                output_questions = structured_llm.invoke(gen_questions_prompt)
                logger.info("[Q&C PAIR] processed chunk %s/%s", i, total_chunks)
                return [
                    Document(
                        page_content=q_text,
                        metadata={
                            "document_title": self.document_title,
                            "chatbot": filter_value,
                            "metadata": json.dumps(
                                {
                                    "chatbot": filter_value,
                                    "document_title": self.document_title,
                                    "page_number": str(chunk.metadata.get("page_number")),
                                    "document_chunk": chunk.page_content,
                                }
                            ),
                        },
                    )
                    for q_text in [output_questions.question1, output_questions.question2, output_questions.question3]
                ]
            except Exception as exc:
                logger.error("[Q&C PAIR] chunk %s failed: %s", i, exc)
                return []

        with ThreadPoolExecutor(max_workers=self.settings.ingest_max_workers) as executor:
            futures = {
                executor.submit(_enrich_one, i, chunk): i
                for i, chunk in enumerate(chunks, start=1)
            }
            for future in as_completed(futures):
                docs = future.result()
                upload_batch.extend(docs)
                total_docs += len(docs)
                if len(upload_batch) >= upload_batch_size:
                    self.upload_chunk_to_ai_search(upload_batch)
                    upload_batch = []

        if upload_batch:
            self.upload_chunk_to_ai_search(upload_batch)

        return total_docs

    def upload_chunk_to_ai_search(self, docs: list[Document]) -> None:
        if not docs:
            return
        try:
            logger.info("[UPLOAD TO AISEARCH] uploading %s docs to index", len(docs))
            self.runtime.kb_search.add_documents(docs)
        except Exception as exc:
            # App-side ingestion logs and continues on upload errors.
            logger.error("[UPLOAD TO AISEARCH] Error uploading to AI Search: %s", exc)

    def ingest_document(self) -> None:
        ingest_started = _log_step_start(
            "document_ingestion",
            chatbot_id=self.chatbot_id,
            chatbot_name=self.chatbot_name,
            document_title=self.document_title,
            document_path=self.document_path,
            document_type=self.document_type,
        )

        step_started = _log_step_start("download_blob", document_path=self.document_path)
        doc_bytes = self.get_file_from_blob_storage()
        _log_step_done("download_blob", step_started, bytes=_safe_len(doc_bytes))

        if self.document_type == "docx":
            step_started = _log_step_start("convert_docx_to_pdf", input_bytes=_safe_len(doc_bytes))
            doc_bytes = self.convert_docx_to_pdf_bytes(doc_bytes)
            _log_step_done("convert_docx_to_pdf", step_started, output_bytes=_safe_len(doc_bytes))

        step_started = _log_step_start("document_intelligence_extract", input_bytes=_safe_len(doc_bytes))
        docint_res = self.extract_from_doc_bytes(doc_bytes)
        content_len = len(docint_res.content or "")
        _log_step_done("document_intelligence_extract", step_started, content_length=content_len)

        step_started = _log_step_start("reconstruct_page_numbers", content_length=content_len)
        content = self.reconstruct_page_numbers(docint_res.content)
        _log_step_done("reconstruct_page_numbers", step_started, output_length=len(content))

        # Keep same flow as app: mutate extracted content before enhancement.
        docint_res.content = content

        step_started = _log_step_start("enhance_extraction_result", page_breaks=content.count(self.page_break))
        enhanced = self.enhance_extraction_result(docint_res)
        _log_step_done("enhance_extraction_result", step_started, output_length=len(enhanced))

        step_started = _log_step_start("chunk_markdown", input_length=len(enhanced))
        chunks = self.chunk_markdown(enhanced)
        _log_step_done("chunk_markdown", step_started, chunk_count=len(chunks))

        step_started = _log_step_start("enrich_and_upload_chunks", chunk_count=len(chunks), workers=self.settings.ingest_max_workers)
        total_docs = self.enrich_and_upload_chunks(chunks)
        _log_step_done("enrich_and_upload_chunks", step_started, generated_docs=total_docs)

        _log_step_done("document_ingestion", ingest_started)


class QnAIngestor:
    def __init__(self, runtime: IngestionRuntime, chatbot_id: str, chatbot_name: str, document_title: str, document_path: str):
        self.runtime = runtime
        self.settings = runtime.settings
        self.chatbot_id = chatbot_id
        self.chatbot_name = chatbot_name
        self.document_title = document_title
        self.document_path = document_path

    def _filter_value(self) -> str:
        # Keep ingestion filter key consistent with app retrievers.
        return self.chatbot_id

    def get_file_from_blob_storage(self) -> pd.DataFrame | None:
        try:
            blob_client = BlobClient(
                account_url=self.settings.storage_url,
                container_name=self.settings.container_name,
                credential=self.settings.storage_key,
                blob_name=self.document_path,
            )
            stream = io.BytesIO()
            blob_client.download_blob().readinto(stream)
            stream.seek(0)
            df = pd.read_excel(stream, engine="openpyxl")
            df = df.where(pd.notna(df), None)
            return df
        except Exception:
            return None

    def upload_to_ai_search(self, df: pd.DataFrame) -> None:
        filter_value = self._filter_value()

        qna_docs: list[Document] = []
        for row in df.to_dict("records"):
            question = row.get("Question")
            if not question:
                continue
            qna_docs.append(
                Document(
                    page_content=str(question),
                    metadata={
                        "qna_filename": self.document_title,
                        "chatbot": filter_value,
                        "metadata": json.dumps(
                        {
                            "chatbot": filter_value,
                            "qna_filename": self.document_title,
                            "document_title": row.get("Source"),
                            "page_number": row.get("Page"),
                            "expected_answer": row.get("Expected answer"),
                        }
                        ),
                    },
                )
            )
        try:
            logger.info("[UPLOAD TO AISEARCH] uploading %s qna rows to index", len(qna_docs))
            self.runtime.qna_search.add_documents(qna_docs)
        except Exception as exc:
            # App-side ingestion logs and continues on upload errors.
            logger.error("[UPLOAD TO AISEARCH] Error uploading QnA rows: %s", exc)

    def ingest_qna(self) -> None:
        ingest_started = _log_step_start(
            "qna_ingestion",
            chatbot_id=self.chatbot_id,
            chatbot_name=self.chatbot_name,
            document_title=self.document_title,
            document_path=self.document_path,
        )

        step_started = _log_step_start("download_qna_blob", document_path=self.document_path)
        df = self.get_file_from_blob_storage()
        _log_step_done("download_qna_blob", step_started, row_count=(len(df.index) if df is not None else 0))

        step_started = _log_step_start("upload_qna_to_ai_search", row_count=(len(df.index) if df is not None else 0))
        self.upload_to_ai_search(df)
        _log_step_done("upload_qna_to_ai_search", step_started)

        _log_step_done("qna_ingestion", ingest_started)


def process_file_ingestion(runtime: IngestionRuntime, chatbot_id: str, chatbot_name: str, document_type: str, document_title: str, document_path: str) -> None:
    step_started = _log_step_start(
        "route_ingestion_type",
        document_type=document_type,
        document_title=document_title,
        chatbot_id=chatbot_id,
    )
    if document_type == "QNA":
        QnAIngestor(runtime, chatbot_id, chatbot_name, document_title, document_path).ingest_qna()
        _log_step_done("route_ingestion_type", step_started, selected="QNA")
    else:
        DocumentIngestor(runtime, chatbot_id, chatbot_name, document_title, document_path).ingest_document()
        _log_step_done("route_ingestion_type", step_started, selected="KNOWLEDGE_BASE")
