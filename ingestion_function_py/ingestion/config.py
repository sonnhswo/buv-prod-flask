import os
from dataclasses import dataclass


@dataclass
class Settings:
    pg_host: str
    pg_user: str
    pg_password: str
    pg_port: str
    pg_database: str
    aoai_key: str
    aoai_endpoint: str
    ingest_model_name: str
    ingest_model_api_version: str
    deterministic_tmp: float
    creative_tmp: float
    vector_search_profile_name: str
    embedding_model_name: str
    embedding_model_api_version: str
    doc_int_endpoint: str
    doc_int_key: str
    ai_search_endpoint: str
    ai_search_key: str
    index_name: str
    phase1_index_name: str
    qna_index_name: str
    storage_url: str
    storage_key: str
    container_name: str
    docx_to_pdf_api_url: str
    timeout: int
    chunk_size: int
    chunk_overlap: int
    ingest_max_workers: int
    phase1_chatbots: set[str]


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    container_name = os.getenv("BLOB_CONTAINER_NAME") or os.getenv("CONTAINER_NAME")
    if not container_name:
        raise ValueError("Missing required environment variable: BLOB_CONTAINER_NAME or CONTAINER_NAME")

    phase1_raw = os.getenv("PHASE1_CHATBOTS", "")
    phase1_chatbots = {x.strip() for x in phase1_raw.split(",") if x.strip()}

    return Settings(
        pg_host=_required("PG_VECTOR_HOST"),
        pg_user=_required("PG_VECTOR_USER"),
        pg_password=_required("PG_VECTOR_PASSWORD"),
        pg_port=os.getenv("PGPORT", "5432"),
        pg_database=_required("PGDATABASE6"),
        aoai_key=_required("AZURE_OPENAI_API_KEY"),
        aoai_endpoint=_required("AZURE_OPENAI_ENDPOINT").rstrip("/"),
        ingest_model_name=_required("AZURE_INGEST_MODEL_DEPLOYMENT_NAME"),
        ingest_model_api_version=_required("AZURE_INGEST_MODEL_DEPLOYMENT_VERSION"),
        deterministic_tmp=float(os.getenv("DETERMINISTIC_TMP", "0")),
        creative_tmp=float(os.getenv("CREATIVE_TMP", "1")),
        vector_search_profile_name=_required("VECTOR_SEARCH_PROFILE"),
        embedding_model_name=_required("AZURE_EMBEDDING_MODEL_DEPLOYMENT_NAME"),
        embedding_model_api_version=_required("AZURE_EMBEDDING_MODEL_OPENAI_VERSION"),
        doc_int_endpoint=_required("DOC_INT_ENDPOINT"),
        doc_int_key=_required("DOC_INT_KEY"),
        ai_search_endpoint=_required("AI_SEARCH_ENDPOINT").rstrip("/"),
        ai_search_key=_required("AI_SEARCH_KEY"),
        index_name=_required("INDEX_NAME"),
        phase1_index_name=_required("PHASE1_INDEX_NAME"),
        qna_index_name=_required("QNA_INDEX_NAME"),
        storage_url=_required("STORAGE_URL"),
        storage_key=_required("STORAGE_KEY"),
        container_name=container_name,
        docx_to_pdf_api_url=_required("DOCX_TO_PDF_API_URL"),
        timeout=int(os.getenv("TIMEOUT", "60")),
        chunk_size=int(os.getenv("CHUNK_SIZE", "1000")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
        ingest_max_workers=int(os.getenv("INGEST_MAX_WORKERS", "3")),
        phase1_chatbots=phase1_chatbots,
    )
