from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from typing import Dict

from langchain_postgres.vectorstores import PGVector
from langchain_core.vectorstores import VectorStoreRetriever
from langchain.retrievers import MultiVectorRetriever
from langchain.retrievers.multi_vector import SearchType

from config import Config
from app.llm_models.embeddings import text_embedding_3large
from app.custom_docstore import PostgresStore

config = Config()


uni_dbs = {
    "British University Vietnam": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PGDATABASE}", 
    "Staffordshire University": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.DEMO_SU}",
    "University of London": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PROD_UOL}",
    "International Foundation Programme": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PROD_IFP}",
    "Arts University Bournemouth": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PROD_AUB}",
    "University of Stirling": f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PROD_US}"
}
print(f"{uni_dbs=}")

def initialize_retrievers() -> tuple[Dict[str, MultiVectorRetriever], Dict[str, VectorStoreRetriever]]:
    doc_retriever_dict = {}
    question_retriever_dict = {}
    for uni_name, connection_string in uni_dbs.items():
    
        vectorstore = PGVector(
            embeddings=text_embedding_3large,
            collection_name=config.COLLECTION_NAME,
            connection=connection_string,
        )
    
        id_key = "doc_id"
        doc_retriever = MultiVectorRetriever(
            vectorstore=vectorstore,
            docstore=PostgresStore(connection_string=connection_string),
            id_key=id_key,
            search_kwargs={"k": 6, "fetch_k": 8}
        )
        question_retriever = vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 3, "lambda_mult": 0})
        doc_retriever.search_type = SearchType.mmr
        doc_retriever_dict[uni_name] = doc_retriever
        question_retriever_dict[uni_name] = question_retriever
    return doc_retriever_dict, question_retriever_dict


