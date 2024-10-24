from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from langchain.vectorstores.pgvector import PGVector
from langchain.retrievers import MultiVectorRetriever
from langchain.retrievers.multi_vector import SearchType

from config import Config
from app.models.embeddings import text_embedding_3large
from app.custom_docstore import PostgresStore

config = Config()


db = SQLAlchemy()

def init_db(app: Flask):
    db.init_app(app)
    with app.app_context():
        db.create_all()


def get_retriever(uni_name: str) -> MultiVectorRetriever:
    if uni_name == "British University Vietnam":
        connection_string = f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PGDATABASE}" # use psycopg3 driver
    elif uni_name == "Staffordshire University":
        connection_string = f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.DEMO_SU}" # use psycopg3 driver
    else:
        # Print error message
        print("Error: Invalid university name")
        return
    
    vectorstore = PGVector(
        embeddings=text_embedding_3large,
        collection_name=config.COLLECTION_NAME,
        connection=connection_string,
    )
    
    id_key = "doc_id"
    retriever = MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=PostgresStore(connection_string=connection_string),
        id_key=id_key,
        search_kwargs={"k": 6, "fetch_k": 8}
    )
    retriever.search_type = SearchType.mmr

    return retriever


