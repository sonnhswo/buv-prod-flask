
from azure.search.documents.indexes.models import SearchField, SearchFieldDataType, SimpleField
from azure.ai.documentintelligence import DocumentIntelligenceClient 
from langchain_community.vectorstores.azuresearch import AzureSearch
from azure.core.credentials import AzureKeyCredential 

from app.llm_models.embeddings import text_embedding_3large
from config import Config

config = Config()

# format for ai search's index fields
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
        vector_search_profile_name = config.VECTOR_SEARCH_PROFILE,
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
        vector_search_profile_name = config.VECTOR_SEARCH_PROFILE,
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
# document extraction
doc_int_client = DocumentIntelligenceClient(
    endpoint   = config.DOC_INT_ENDPOINT,
    credential = AzureKeyCredential(config.DOC_INT_KEY)
)
# knowledge base - storage & retrieval
ai_search = AzureSearch (
    azure_search_endpoint = config.AI_SEARCH_ENDPOINT,
    azure_search_key      = config.AI_SEARCH_KEY,
    index_name            = config.INDEX_NAME,
    embedding_function    = text_embedding_3large,
    fields                = index_fields,
)
# phase 1 migrated knowledge base
phase1_ai_search = AzureSearch (
    azure_search_endpoint = config.AI_SEARCH_ENDPOINT,
    azure_search_key      = config.AI_SEARCH_KEY,
    index_name            = config.PHASE1_INDEX_NAME,
    embedding_function    = text_embedding_3large.embed_query,
    fields                = index_fields,
)
# QnA knowledge base
qna_ai_search = AzureSearch(
    azure_search_endpoint = config.AI_SEARCH_ENDPOINT,
    azure_search_key      = config.AI_SEARCH_KEY,
    index_name            = config.QNA_INDEX_NAME,
    embedding_function    = text_embedding_3large.embed_query,
    fields                = qna_fields,
)