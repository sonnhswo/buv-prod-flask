import json
import io
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobClient
from langchain_core.documents import Document
from langchain_text_splitters.markdown import RecursiveCharacterTextSplitter
from openai import AzureOpenAI

from .config import Settings


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
        return self.chatbot_name if self.chatbot_name in self.settings.phase1_chatbots else self.chatbot_id

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
        response = requests.post(self.settings.docx_to_pdf_api_url, files=files, timeout=self.settings.timeout)
        response.raise_for_status()
        return response.content

    def extract_from_doc_bytes(self, file_bytes: bytes) -> AnalyzeResult:
        poller = self.runtime.doc_int_client.begin_analyze_document(
            "prebuilt-layout",
            body=file_bytes,
            output_content_format="markdown",
        )
        return poller.result()

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

    def enhance_extraction_result(self, markdown_text: str) -> str:
        pages = markdown_text.split(self.page_break)
        outputs = []
        for page in pages:
            prompt = (
                "You are an expert text reformater. Preserve all content and keep each page marker "
                "like <!-- PageNumber=\\\"n\\\" --> exactly unchanged. Return only improved markdown "
                "with better structure.\n\nInput:\n"
                f"{page}"
            )
            fixed = self.runtime.chat_completion(prompt, temperature=0)
            outputs.append(fixed if fixed else page)
        return "\n".join(outputs)

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

    def enrich_chunks(self, chunks: list[Document]) -> list[dict]:
        filter_value = self._filter_value()
        results: list[dict] = []

        def worker(chunk: Document):
            q1, q2, q3 = self._generate_questions(chunk.page_content)
            payload = []
            for q_text in (q1, q2, q3):
                payload.append(
                    {
                        "content": q_text,
                        "metadata": {
                            "chatbot": filter_value,
                            "document_title": self.document_title,
                            "page_number": str(chunk.metadata.get("page_number")),
                            "document_chunk": chunk.page_content,
                        },
                    }
                )
            return payload

        with ThreadPoolExecutor(max_workers=max(1, self.settings.ingest_max_workers)) as executor:
            futures = [executor.submit(worker, chunk) for chunk in chunks]
            for future in as_completed(futures):
                results.extend(future.result())

        return results

    def upload_chunk_to_ai_search(self, docs: list[dict]) -> None:
        if not docs:
            return

        index_name = self.settings.phase1_index_name if self.chatbot_name in self.settings.phase1_chatbots else self.settings.index_name
        url = f"{self.settings.ai_search_endpoint}/indexes/{index_name}/docs/index?api-version=2024-07-01"

        actions = []
        for doc in docs:
            actions.append(
                {
                    "@search.action": "upload",
                    "id": str(uuid.uuid4()),
                    "content": doc["content"],
                    "content_vector": self.runtime.embedding(doc["content"]),
                    "metadata": json.dumps(doc["metadata"]),
                }
            )

        resp = requests.post(
            url,
            headers={"Content-Type": "application/json", "api-key": self.settings.ai_search_key},
            json={"value": actions},
            timeout=self.settings.timeout * 2,
        )
        resp.raise_for_status()

    def ingest_document(self) -> None:
        doc_bytes = self.get_file_from_blob_storage()
        if self.document_type == "docx":
            doc_bytes = self.convert_docx_to_pdf_bytes(doc_bytes)

        docint_res = self.extract_from_doc_bytes(doc_bytes)
        content = self.reconstruct_page_numbers(docint_res.content)
        enhanced = self.enhance_extraction_result(content)
        chunks = self.chunk_markdown(enhanced)
        qc_pairs = self.enrich_chunks(chunks)
        self.upload_chunk_to_ai_search(qc_pairs)


class QnAIngestor:
    def __init__(self, runtime: IngestionRuntime, chatbot_id: str, chatbot_name: str, document_title: str, document_path: str):
        self.runtime = runtime
        self.settings = runtime.settings
        self.chatbot_id = chatbot_id
        self.chatbot_name = chatbot_name
        self.document_title = document_title
        self.document_path = document_path

    def _filter_value(self) -> str:
        return self.chatbot_name if self.chatbot_name in self.settings.phase1_chatbots else self.chatbot_id

    def get_file_from_blob_storage(self) -> bytes:
        blob_client = BlobClient(
            account_url=self.settings.storage_url,
            container_name=self.settings.container_name,
            credential=self.settings.storage_key,
            blob_name=self.document_path,
        )
        return blob_client.download_blob().readall()

    def upload_to_ai_search(self, df: pd.DataFrame) -> None:
        url = f"{self.settings.ai_search_endpoint}/indexes/{self.settings.qna_index_name}/docs/index?api-version=2024-07-01"
        filter_value = self._filter_value()

        actions = []
        for row in df.to_dict("records"):
            question = row.get("Question")
            if not question:
                continue
            actions.append(
                {
                    "@search.action": "upload",
                    "id": str(uuid.uuid4()),
                    "content": str(question),
                    "content_vector": self.runtime.embedding(str(question)),
                    "metadata": json.dumps(
                        {
                            "chatbot": filter_value,
                            "qna_filename": self.document_title,
                            "document_title": row.get("Source") or self.document_title,
                            "page_number": row.get("Page"),
                            "expected_answer": row.get("Expected answer"),
                        }
                    ),
                }
            )

        resp = requests.post(
            url,
            headers={"Content-Type": "application/json", "api-key": self.settings.ai_search_key},
            json={"value": actions},
            timeout=self.settings.timeout * 2,
        )
        resp.raise_for_status()

    def ingest_qna(self) -> None:
        file_bytes = self.get_file_from_blob_storage()
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
        self.upload_to_ai_search(df)


def process_file_ingestion(runtime: IngestionRuntime, chatbot_id: str, chatbot_name: str, document_type: str, document_title: str, document_path: str) -> None:
    if (document_type or "").upper() == "QNA":
        QnAIngestor(runtime, chatbot_id, chatbot_name, document_title, document_path).ingest_qna()
    else:
        DocumentIngestor(runtime, chatbot_id, chatbot_name, document_title, document_path).ingest_document()
