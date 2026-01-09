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


def build_connection_string(database_name: str) -> str:
    """Build PostgreSQL connection string for a given database name."""
    return f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{database_name}"


def load_chatbot_database_mappings() -> Dict[str, str]:
    """Load chatbot to database mappings from the database."""
    from app.db_models.raw_db import Chatbot

    chatbots = Chatbot.query.all()
    uni_dbs = {}

    for chatbot in chatbots:
        full_name = config.AB_CONFIGS.get(chatbot.name, {}).get("full_name")
        if full_name and chatbot.database_name:
            connection_string = build_connection_string(chatbot.database_name)
            uni_dbs[full_name] = connection_string

    print(f"{uni_dbs=}")
    return uni_dbs

def initialize_retrievers(app=None) -> tuple[Dict[str, MultiVectorRetriever], Dict[str, VectorStoreRetriever]]:
    doc_retriever_dict = {}
    question_retriever_dict = {}

    # Load database mappings from the database
    # If app context is provided, use it; otherwise try to use current context
    if app:
        with app.app_context():
            uni_dbs = load_chatbot_database_mappings()
    else:
        uni_dbs = load_chatbot_database_mappings()

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


