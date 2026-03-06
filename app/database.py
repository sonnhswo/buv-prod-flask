from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from typing import List
from pydantic import Field

from app.azure_clients.kb_clients import get_ai_search, get_qna_ai_search
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

class AzureAISearchRetriever(BaseRetriever):
    chatbot: str = Field(..., description="Chatbot id for filtering")
    chatbot_name: str = Field(..., description="Chatbot name for legacy checking")
    k: int = Field(default=3, description="Number of documents to return")

    def _get_relevant_documents(self, query: str) -> List[Document]:
        print(f"[AI SEARCH RETRIEVER] Searching (k={self.k})")

        knowledge_base = get_ai_search()

        filter_value = self.chatbot

        # Use the MMR-specific method for diversity
        search_results_with_score = knowledge_base.max_marginal_relevance_search_with_score(
            query       = query,
            k           = self.k,        # Uses the k passed during initialization (6 or 3)
            fetch_k     = config.FETCH_K,            # Candidates for diversity processing
            lambda_mult = config.LAMBDA_MULT,           # Balanced diversity/relevance
            filters     = f"chatbot eq '{filter_value}'" 
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

class QuestionRetriever(BaseRetriever):
    chatbot: str = Field(..., description="Chatbot id for filtering")
    chatbot_name: str = Field(..., description="Chatbot name for legacy checking")
    k: int = Field(default=3, description="Number of questions to return")

    def _get_relevant_documents(self, query: str) -> List[Document]:
        print(f"[QUESTION RETRIEVER] Searching (k={self.k})")

        knowledge_base = get_ai_search()
        filter_value = self.chatbot

        search_results = knowledge_base.similarity_search(
            query       = query,
            k           = config.QUESTION_TOP_K,
            search_type = "similarity",
            filters     = f"chatbot eq '{filter_value}'" 
        )
        print(f"[QUESTION RETRIEVER] Found {len(search_results)} documents.")

        # Fallback: top up with arbitrary docs 
        if len(search_results) < self.k:

            shortfall = self.k - len(search_results)
            print(f"[QUESTION RETRIEVER][WARN] Short by {shortfall}, pulling arbitrary docs...")

            fallback_results = knowledge_base.similarity_search(
            query       = "",
            k           = config.QUESTION_TOP_K,
            search_type = "similarity",
            filters     = f"chatbot eq '{filter_value}'" 
        )
            for doc in fallback_results:
                search_results.append(doc)

        list_docs = []
        for doc_obj in search_results:
            doc = Document(
                page_content = doc_obj.metadata.get("document_chunk", "No content found"),
                metadata     = {
                    "title":            doc_obj.metadata.get("document_title"),
                    "page_number":      doc_obj.metadata.get("page_number"),
                    "matched_question": doc_obj.page_content
                }
            )
            list_docs.append(doc)

        return list_docs
    
class QnARetriever(BaseRetriever):
    chatbot: str = Field(..., description="Chatbot id for filtering")
    chatbot_name: str = Field(..., description="Chatbot name for legacy checking")
    k: int = Field(default=1, description="Number of documents to return")

    def _get_relevant_documents(self, query: str) -> List[Document]:
        print(f"[QNA RETRIEVER] Searching (k={self.k})")
        
        filter_value = self.chatbot

        # Retrieve k documents that passes the threshold
        search_results_with_score = get_qna_ai_search().similarity_search_with_relevance_scores(
            query = query,
            k = self.k,
            score_threshold = config.QNA_SIMILARITY_THRESHOLD,
            filters = f"chatbot eq '{filter_value}'"
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

def delete_qna(chatbot_id: str, chatbot_name: str, document_name: str) -> int: 
    """
    Delete the QnA file from knowledge base.

    :param chatbot_id: the ID of the chatbot that owns this QnA file.
    :type chatbot_id: str
    :param chatbot_name: the name of the chatbot for legacy checking.
    :type chatbot_name: str
    :param document_name: the name of the QnA file (exactly as Document.name in PostgresDb).
    :type document_name: str
    :return: the number of rows successfully deleted, -1 in the case of failure.
    :rtype: int    
    """
    try: 
        print(f"[DELETING QNA] starting deletion for {document_name}, of bot {chatbot_name}")
        
        # Select the right field value to filter by
        filter_value = chatbot_id
        
        docs_to_delete = get_qna_ai_search().client.search(
            "*",
            select = ["id"],
            filter = f"chatbot eq '{filter_value}' and qna_filename eq '{document_name}'"
        )
        ids_to_delete = [ doc.get("id") for doc in docs_to_delete ]

        nb_rows_deleted = len(ids_to_delete)
        get_qna_ai_search().delete(ids_to_delete)
        
        print(f"[DELETING QNA] deleted {nb_rows_deleted} rows successfully")
        return nb_rows_deleted
    except Exception as e:
        print(f"[DELETING QNA] deletion failed with error: \n{e}")
        return -1

def delete_doc_from_kb(chatbot_id: str, chatbot_name: str, document_name: str) -> int: 
    """
    Delete the document file from knowledge base.

    :param chatbot_id: the id of the chatbot that owns this document.
    :type chatbot_id: str
    :param document_name: the name of the document (exactly as Document.name in PostgresDb).
    :type document_name: str
    :return: the number of document chunks successfully deleted, -1 in the case of failure.
    :rtype: int    
    """
    try: 
        print(f"[DELETING DOC] starting deletion for {document_name}, of bot {chatbot_name}")

        knowledge_base = get_ai_search()
        filter_value = chatbot_id
        docs_to_delete = knowledge_base.client.search(
            "*",
            select = ["id"],
            filter = f"chatbot eq '{filter_value}' and document_title eq '{document_name}'"
        )
        ids_to_delete = [ doc.get("id") for doc in docs_to_delete ]

        nb_rows_deleted = len(ids_to_delete)
        knowledge_base.delete(ids_to_delete)
        
        print(f"[DELETING DOC] deleted {nb_rows_deleted} docs successfully")
        return nb_rows_deleted
    except Exception as e:
        print(f"[DELETING DOC] deletion failed with error: \n{e}")
        return -1
