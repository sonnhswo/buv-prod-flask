from langchain_text_splitters.markdown import RecursiveCharacterTextSplitter
from azure.ai.documentintelligence.models import AnalyzeResult
from langchain_core.documents import Document
from azure.storage.blob import BlobClient

from pydantic import BaseModel, Field
from typing import Optional
import pandas as pd
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import re
import io

from app.azure_clients.kb_clients import doc_int_client, ai_search, phase1_ai_search, qna_ai_search
from app.llm_models.chat_models import llm_fixer, llm_generator
from app.database import phase1_chatbots
from config import Config

config = Config()

# Structured output for LLM chunk enriching
class ChunkQuestions(BaseModel):
    question1: str = Field(description="A general question covering the main idea, topic, or purpose of the content. If the input is already a question, preserve it here.")
    question2: str = Field(description="A question probing deeper into specific details, implications, or data points found within the content.")
    question3: str = Field(description="A question addressing applications, consequences, or relationships between different elements in the content.")


class DocumentIngestor :

    def __init__(self, chatbot_id: str, chatbot_name: str, document_title: str, document_path: str):
        """
        Class wrapper to handle document ingestion from Blob Storage to knowledge base on AI Search.

        chatbot_id : unique ID of chatbot.
        document_title : name of the document exactly as the one on blob storage (ex: "Student_Handbook_2025.pdf").
        """
        self.chatbot_id = chatbot_id
        self.chatbot_name = chatbot_name
        self.document_title = document_title
        self.document_path = document_path
        self.document_type = document_title.split('.')[-1]

        self.PAGE_RE = re.compile(r'<!-- PageNumber="(\d+)" -->')
        self.PAGE_BREAK = "<!-- PageBreak -->"

    # ----------------------------------------------------------------------------------------------- #

    def convert_docx_to_pdf_bytes(self, docx_bytes):
        """
        Automates DOCX to PDF conversion.
        """
        files = {
            'file': (
                self.document_title, 
                io.BytesIO(docx_bytes), 
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document' # MIME Type
            )
        }
        try:
            print(f"[CONVERT DOCX TO PDF] Converting {self.document_title} to PDF...")
            response = requests.post(config.DOCX_TO_PDF_API_URL, files=files, timeout=config.TIMEOUT)
            response.raise_for_status()
            print(f"[CONVERT DOCX TO PDF] Completed converting {self.document_title} to PDF")
            return response.content

        except requests.exceptions.RequestException as e:
            print(f"Error during PDF conversion: {e}")
            return None

    # ----------------------------------------------------------------------------------------------- #
    
    def reconstruct_page_numbers(self, text: str) -> str:
        """
        Reconstruct missing <!-- PageNumber="n" --> markers.
        - If <!-- PageBreak --> exists (Paginated doc like PDF), use it.
        - If not (Doc like DOCX), approximate 3000 characters per page.
        """
        if self.PAGE_BREAK in text:
            print("[RECONSTRUCT PAGE NUMBERS] Reconstructing page numbers...")
            pages = text.split(self.PAGE_BREAK)
            new_pages = []
            
            for i, page_content in enumerate(pages):
                page_num = i + 1
                page_content = self.PAGE_RE.sub("\n", page_content).strip()
                page_content = f'\n<!-- PageNumber="{page_num}" -->\n' + page_content.lstrip() + '\n'
                new_pages.append(page_content)
            
            return self.PAGE_BREAK.join(new_pages)
        else:
            print("[RECONSTRUCT PAGE NUMBERS] No page breaks found, approximating page numbers...")
            # DOCX / Non-paginated heuristic: 3000 chars = 1 page
            page_size = 3000
            new_content = []
            for i in range(0, len(text), page_size):
                page_num = (i // page_size) + 1
                segment = text[i : i + page_size]
                new_content.append(f'<!-- PageNumber="{page_num}" -->\n' + segment)
            
            return "\n".join(new_content)
    
    # ----------------------------------------------------------------------------------------------- #

    def get_file_from_blob_storage(self) -> Optional[bytes] :
        """
        Read and return the content of a file housed on blob storage.
        
        :param filename: file name on blob storage.
        :type filename: str
        :return: the file content as bytes.
        :rtype: bytes | None
        """
        try:
            print(f"[GET FILE FROM BLOB] Starting {self.document_path} download...")
            blob_client = BlobClient(
                account_url    = config.STORAGE_URL,
                container_name = config.CONTAINER_NAME,
                credential     = config.STORAGE_KEY,
                blob_name      = self.document_path
            )
            doc_bytes = blob_client.download_blob().readall()
            return doc_bytes

        except Exception as e :
            return None

    # ----------------------------------------------------------------------------------------------- #

    def extract_from_doc_bytes(self, file: bytes) -> Optional[AnalyzeResult] :
        """
        Call Document Intelligence client to extract information from file.
        
        :param file: file in bytes.
        :type file: bytes
        :return: Azure document analysis result object.
        :rtype: AnalyzeResult | None
        """
        try :
            print("[EXTRACT FROM DOC] Starting extraction...")
        
            poller = doc_int_client.begin_analyze_document( "prebuilt-layout", 
                                                            body = file, 
                                                            output_content_format = "markdown" )
            result : AnalyzeResult = poller.result()
            return result
        
        except Exception as e :
            return None
        
    # ----------------------------------------------------------------------------------------------- #

    def enhance_extraction_result(self, result: AnalyzeResult) -> str:
        """
        Call LLM to enhance the extraction result from Document Intelligence.

        :param result: result object from running Document Intelligence.
        :type chunks: AnalyzeResult
        :return: A string containing the enhanced document, written in Markdown.
        :rtype: str
        """

        lcontent = result.content.split("<!-- PageBreak -->")

        lenhanced = []

        for content in lcontent:
            enhance_extraction_prompt = \
            f"""
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
            resp = llm_fixer.invoke(enhance_extraction_prompt)
            lenhanced.append(resp.content)
        
        return "\n".join(lenhanced)
 
    # ----------------------------------------------------------------------------------------------- #

    def attach_page_metadata(self, chunks: list[Document]) -> list[Document]:
        """
        Attaches page numbers to chunks, ensuring chunks that don't 
        contain a marker inherit the page number from the previous one.
        If no markers are found at all, page_number defaults to [0].
        """
        current_page = 0 # Default is 0 for non-paginated docs

        for chunk in chunks:
            # 1. Find all page markers in THIS chunk [1], [2], [3], etc.
            found_pages = sorted({int(p) for p in self.PAGE_RE.findall(chunk.page_content)})
            
            if found_pages: 
                # If markers are found, this chunk belongs to these pages
                chunk.metadata["page_number"] = [found_pages[0]-1] + found_pages if current_page else found_pages
                # Update our "sticky" tracker to the last page found in this chunk
                current_page = found_pages[-1]
            else:
                # Inherit last known page (will be [0] if none found yet)
                chunk.metadata["page_number"] = [current_page]

            # 2. Clean up the content by removing the markers
            chunk.page_content = self.PAGE_RE.sub("", chunk.page_content).strip()
        
        print(f"[ATTACH PAGE METADATA] Completed attaching page metadata.")
        return chunks

    # ----------------------------------------------------------------------------------------------- #

    def chunk_markdown(self, text: str) -> list[Document]:
        """
        Chunk text using RecursiveCharacterTextSplitter.

        :param text: The text to be chunked.
        :type text: str
        :return: The list of chunks.
        :rtype: list[Document]
        """
        print(f"[CHUNKING] Started chunking document.")

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
            separators=["\n\n", "\n", " ", ""]
        )

        final_chunks = splitter.split_documents( [Document(page_content=text)] )
        print(f"[CHUNKING] Chunked document into {len(final_chunks)} chunks.")

        return self.attach_page_metadata(final_chunks)

    # ----------------------------------------------------------------------------------------------- #

    def enrich_chunks(self, chunks: list[Document], max_workers: int = 5) -> list[Document] :
        """
        Enrich chunks by generating 3 questions for each chunk using structured output.
        Chunks are processed in parallel using a thread pool.

        :param chunks: list of chunks
        :type chunks: list[Document]
        :param max_workers: max concurrent LLM calls (tune based on your API rate limit)
        :type max_workers: int
        :return: A list of chunks representing Question - Chunk pairs, that is ready for upload.
        :rtype: list[Document]
        """
        print(f"[Q&C PAIR] Started generating questions for {len(chunks)} chunks.")

        # Initialize structured LLM (thread-safe: stateless HTTP client)
        structured_llm = llm_generator.with_structured_output(ChunkQuestions)

        filter_value = self.chatbot_name if self.chatbot_name in phase1_chatbots else self.chatbot_id

        counter = 0
        lock = threading.Lock()

        def process_chunk(args):
            nonlocal counter
            i, chunk = args

            gen_questions_prompt = \
            f"""
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

            output_questions = structured_llm.invoke(gen_questions_prompt)

            with lock:
                counter += 1
                print(f"-- Processing chunk: {counter}/{len(chunks)}", end="\r")

            return i, chunk, output_questions

        # Submit all chunks in parallel, preserving original order
        results = [None] * len(chunks)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(process_chunk, (i, chunk)): i
                for i, chunk in enumerate(chunks)
            }
            for future in as_completed(future_to_index):
                i = future_to_index[future]
                try:
                    _, chunk, output_questions = future.result()
                    results[i] = (chunk, output_questions)
                except Exception as e:
                    print(f"\n[Q&C PAIR] /!\\ Chunk {i} failed: {e}")

        # Build final list in original chunk order
        enhanced = []
        for item in results:
            if item is None:
                continue
            chunk, output_questions = item
            for q_text in [output_questions.question1, output_questions.question2, output_questions.question3]:
                enhanced.append(
                    Document(
                        page_content = q_text,
                        metadata = {
                            "document_title" : self.document_title,
                            "chatbot"        : filter_value,
                            "metadata"       : json.dumps({
                                "chatbot"       : filter_value,
                                "document_title": self.document_title,
                                "page_number"   : str(chunk.metadata.get("page_number")),
                                "document_chunk": chunk.page_content
                            })
                        }
                    )
                )
        return enhanced

    # ----------------------------------------------------------------------------------------------- #

    def upload_chunk_to_ai_search(self,chunk_list: list[Document]) -> None : 
        """
        upload chunks (also called 'documents' by AISearch) to AISearch
        """
        try :
            print(f"[UPLOAD TO AISEARCH] uploading {len(chunk_list)} docs to index.")

            knowledge_base = phase1_ai_search if self.chatbot_name in phase1_chatbots else ai_search
            knowledge_base.add_documents(chunk_list)
        except Exception as e :
            print(f"[UPLOAD TO AISEARCH] Error uploading to AI Search: {e}")

    # =============================================================================================== #

    def ingest_document(self) -> None:
        """
        Ingest the document present on Blob storage according to the file_path, 
        and save it to the Knowledge Base of chatbot_name.
        """
        print(self.document_path)
        print(self.chatbot_id)
        # 1. call blob storage
        doc_bytes = self.get_file_from_blob_storage()

        # convert docx->pdf
        if self.document_type == 'docx':
            doc_bytes = self.convert_docx_to_pdf_bytes(doc_bytes)

        # 2. call document intelligence
        docint_res = self.extract_from_doc_bytes(doc_bytes)
        
        # Reconstruct missing page numbers
        doc_content = self.reconstruct_page_numbers(docint_res.content)

        # Update docint_res content for the next step
        docint_res.content = doc_content

        # 3. smart fix/enhance : call LLM
        enhanced_res = self.enhance_extraction_result(docint_res) # temperature = 0

        # 4. chunking
        chunks = self.chunk_markdown(enhanced_res)

        # 5. generate questions
        qc_pairs = self.enrich_chunks(chunks) # temperature = 1.0

        # 6. upload to AI Search
        self.upload_chunk_to_ai_search(qc_pairs)

class QnAIngestor:

    def __init__(self, chatbot_id: str, chatbot_name: str, document_title: str, document_path: str):
        self.chatbot_id = chatbot_id
        self.chatbot_name = chatbot_name
        self.document_title = document_title
        self.document_path = document_path

    # ----------------------------------------------------------------------------------------------- #

    def get_file_from_blob_storage(self) -> pd.DataFrame:
        try:
            print(f"[GET FILE FROM BLOB] Starting {self.document_path} download...")
            
            blob_client = BlobClient(
                account_url    = config.STORAGE_URL,
                container_name = config.CONTAINER_NAME,
                credential     = config.STORAGE_KEY,
                blob_name      = self.document_path
            )
            stream = io.BytesIO()
            blob_client.download_blob().readinto(stream)
            stream.seek(0)
            
            df = pd.read_excel(stream, engine='openpyxl')
            print(f"[GET FILE FROM BLOB] Successfully loaded {len(df)} rows.")
            return df
            
        except Exception as e:
            print(f"[ERROR] Failed to download or parse blob: {e}")
            return None
    
    # ----------------------------------------------------------------------------------------------- #

    def upload_to_ai_search(self, qna_fd: pd.DataFrame) -> None:
        filter_value = self.chatbot_name if self.chatbot_name in phase1_chatbots else self.chatbot_id

        qna_list = []
        for record in qna_fd.to_dict("records"):
            qna_doc = Document(
                page_content = record.get("Question"),
                metadata = {
                    "qna_filename": self.document_title,
                    "chatbot"     : filter_value,
                    "metadata"    : json.dumps({
                        "chatbot"        : filter_value,
                        "document_title" : record.get("Source"),
                        "page_number"    : record.get("Page"),
                        "expected_answer": record.get("Expected answer")
                    })
                }
            )
            qna_list.append(qna_doc)
        try :
            print(f"[UPLOAD TO AISEARCH] uploading {len(qna_list)} rows to index.")
            qna_ai_search.add_documents(qna_list)
            print(f"[UPLOAD TO AISEARCH] upload successful.")
        except Exception as e :
            print(f"[UPLOAD TO AISEARCH] Error: {e}")

    # ----------------------------------------------------------------------------------------------- #
    
    def ingest_qna(self):
        df = self.get_file_from_blob_storage()
        self.upload_to_ai_search(df)

def process_file_ingestion(chatbot_id: str, chatbot_name: str, document_type: str, document_title: str, document_path: str) -> None:
    """
    Helper function to route file ingestion based on document type.
    """
    if document_type == 'QNA':
        ingestor = QnAIngestor(
            chatbot_id=chatbot_id,
            chatbot_name=chatbot_name, 
            document_title=document_title, 
            document_path=document_path
        )
        ingestor.ingest_qna()
    else:
        ingestor = DocumentIngestor(
            chatbot_id=chatbot_id,
            chatbot_name=chatbot_name,
            document_title=document_title, 
            document_path=document_path
        )
        ingestor.ingest_document()
