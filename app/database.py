from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from typing import List, Dict
from pydantic import Field

from app.azure_clients.kb_clients import ai_search, phase1_ai_search
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


chatbot_names = [
        "British University Vietnam",
        "Staffordshire University",
        "University of London",
        "International Foundation Programme",
        "Arts University Bournemouth",
        "University of Stirling",
        "uat_assessment_approval",
        "uat_academic_misconduct",
        "uat_academic_quality", 
        "uat_grade_explanation",
        "uat_marking_moderation",
        "uat_sits_training",
        "uat_student_group_work",
        "uat_teaching_observation",
        "uat_teaching_qualification" 
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


def initialize_retrievers() -> tuple[Dict[str, AzureAISearchRetriever], Dict[str, AzureAISearchRetriever]]:
    """
    Returns two dictionaries: 
    - doc_retriever_dict (k=6)
    - question_retriever_dict (k=3)
    """

    doc_retriever_dict = {}
    question_retriever_dict = {}

    for chatbot_name in chatbot_names:
        # Create distinct retrievers with different k values
        doc_retriever = AzureAISearchRetriever(chatbot=chatbot_name, k=config.DOC_TOP_K)
        question_retriever = AzureAISearchRetriever(chatbot=chatbot_name, k=config.QUESTION_TOP_K)
        
        doc_retriever_dict[chatbot_name] = doc_retriever
        question_retriever_dict[chatbot_name] = question_retriever
        
    return doc_retriever_dict, question_retriever_dict





