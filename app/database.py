from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from typing import List
from pydantic import Field

from app.azure_clients.kb_clients import ai_search, phase1_ai_search, qna_ai_search
from config import Config

config = Config()


uni_dbs = {
    "British University Vietnam": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PGDATABASE}", 
    "Staffordshire University": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.DEMO_SU}",
    "University of London": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PROD_UOL}",
    "International Foundation Programme": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PROD_IFP}",
    "Arts University Bournemouth": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PROD_AUB}",
    "University of Stirling": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PROD_US}"
}

phase1_chatbots = [
    "British University Vietnam",
    "Staffordshire University",
    "University of London",
    "International Foundation Programme",
    "Arts University Bournemouth",
    "University of Stirling"
]

class AzureAISearchRetriever(BaseRetriever):
    chatbot: str = Field(..., description="Chatbot name for filtering")
    k: int = Field(default=3, description="Number of documents to return")

    def _get_relevant_documents(self, query: str) -> List[Document]:
        print(f"[AI SEARCH RETRIEVER] Searching (k={self.k})")

        knowledge_base = ai_search if self.chatbot not in phase1_chatbots else phase1_ai_search

        # Use the MMR-specific method for diversity
        search_results_with_score = knowledge_base.max_marginal_relevance_search_with_score(
            query       = query,
            k           = self.k,        # Uses the k passed during initialization (6 or 3)
            fetch_k     = config.FETCH_K,            # Candidates for diversity processing
            lambda_mult = config.LAMBDA_MULT,           # Balanced diversity/relevance
            filters     = f"chatbot eq '{self.chatbot}'" 
        )
        print(f"Found {len(search_results_with_score)} documents.")

        list_docs = []
        for doc_obj, score in search_results_with_score:
            doc = Document(
                page_content = doc_obj.metadata.get("document_chunk", "No content found"),
                metadata     = { 
                    "title": doc_obj.metadata.get("document_title"),
                    "page_number": doc_obj.metadata.get("page_number"),
                    "matched_question": doc_obj.page_content,
                    "score": score
                }
            )
            list_docs.append(doc)
        
        return list_docs
    
class QnARetriever(BaseRetriever):
    chatbot: str = Field(..., description="Chatbot name for filtering")
    k: int = Field(default=1, description="Number of documents to return")

    def _get_relevant_documents(self, query: str) -> List[Document]:
        print(f"[QNA RETRIEVER] Searching (k={self.k})")

        # Retrieve k documents that passes the threshold
        search_results_with_score = qna_ai_search.similarity_search_with_relevance_scores(
            query = query,
            k = self.k,
            score_threshold = config.QNA_SIMILARITY_THRESHOLD,
            filters = f"chatbot eq '{self.chatbot}'"
        )

        print(f"Found {len(search_results_with_score)} QnAs.")

        list_docs = []
        for doc_obj, score in search_results_with_score:
            doc = Document(
                page_content = doc_obj.metadata.get("expected_answer", "No content found"),
                metadata     = { 
                    "title": doc_obj.metadata.get("document_title"),
                    "page_number": doc_obj.metadata.get("page_number"),
                    "matched_question": doc_obj.page_content,
                    "score": score
                }
            )
            list_docs.append(doc)
        
        return list_docs
    
def delete_qna(chatbot_name: str, document_name: str) -> int: 
    """
    Delete the QnA file from knowledge base.
    
    :param chatbot_name: the name of the chatbot that owns this QnA file.
    :type chatbot_name: str
    :param document_name: the name of the QnA file (exactly as Document.name in PostgresDb).
    :type document_name: str
    :return: the number of rows successfully deleted, -1 in the case of failure.
    :rtype: int    
    """
    try: 
        print(f"[DELETING QNA] starting deletion for {document_name}, of bot {chatbot_name}")
        docs_to_delete = qna_ai_search.client.search(
            "*",
            select = ["id"],
            filter = f"chatbot eq '{chatbot_name}' and qna_filename eq '{document_name}'"
        )
        ids_to_delete = [ doc.get("id") for doc in docs_to_delete ]

        nb_rows_deleted = len(ids_to_delete)
        qna_ai_search.delete(ids_to_delete)
        
        print(f"[DELETING QNA] deleted {nb_rows_deleted} rows successfully")
        return nb_rows_deleted
    except Exception as e:
        print(f"[DELETING QNA] deletion failed with error: \n{e}")
        return -1

def delete_doc_from_kb(chatbot_name: str, document_name: str) -> int: 
    """
    Delete the document file from knowledge base.
    
    :param chatbot_name: the name of the chatbot that owns this document.
    :type chatbot_name: str
    :param document_name: the name of the document (exactly as Document.name in PostgresDb).
    :type document_name: str
    :return: the number of document chunks successfully deleted, -1 in the case of failure.
    :rtype: int    
    """
    try: 
        print(f"[DELETING DOC] starting deletion for {document_name}, of bot {chatbot_name}")

        knowledge_base = ai_search if chatbot_name not in phase1_chatbots else phase1_ai_search
        docs_to_delete = knowledge_base.client.search(
            "*",
            select = ["id"],
            filter = f"chatbot eq '{chatbot_name}' and document_title eq '{document_name}'"
        )
        ids_to_delete = [ doc.get("id") for doc in docs_to_delete ]

        nb_rows_deleted = len(ids_to_delete)
        knowledge_base.delete(ids_to_delete)
        
        print(f"[DELETING DOC] deleted {nb_rows_deleted} docs successfully")
        return nb_rows_deleted
    except Exception as e:
        print(f"[DELETING DOC] deletion failed with error: \n{e}")
        return -1
