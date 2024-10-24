import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(".env"))

class Config:
    AZURE_OPENAI_API_KEY = os.getenv('AZURE_OPENAI_API_KEY')
    AZURE_OPENAI_ENDPOINT = os.getenv('AZURE_OPENAI_ENDPOINT')
    AZURE_CHAT_MODEL_DEPLOYMENT_NAME = os.getenv('AZURE_CHAT_MODEL_DEPLOYMENT_NAME')
    AZURE_CHAT_MODEL_OPENAI_VERSION = os.getenv('AZURE_CHAT_MODEL_OPENAI_VERSION')
    AZURE_EMBEDDING_MODEL_DEPLOYMENT_NAME = os.getenv('AZURE_EMBEDDING_MODEL_DEPLOYMENT_NAME')
    AZURE_EMBEDDING_MODEL_OPENAI_VERSION = os.getenv('AZURE_EMBEDDING_MODEL_OPENAI_VERSION')
    
    BLOB_CONN_STRING = os.getenv('BLOB_CONN_STRING')
    BLOB_CONTAINER = os.getenv('BLOB_CONTAINER')
    
    COLLECTION_NAME = os.getenv('COLLECTION_NAME')
    
    PG_VECTOR_HOST = os.getenv('PG_VECTOR_HOST')
    PG_VECTOR_USER = os.getenv('PG_VECTOR_USER')
    PG_VECTOR_PASSWORD = os.getenv('PG_VECTOR_PASSWORD')
    PGPORT = os.getenv('PGPORT')
    
    PGDATABASE = os.getenv('PGDATABASE') # BUV database
    PGDATABASE2 = os.getenv('PGDATABASE2') # Bus Schedule database
    PGDATABASE3 = os.getenv('PGDATABASE3') # Bus General Info database
    PGDATABASE4 = os.getenv('PGDATABASE4') # Unclear Questions database
    PGDATABASE5 = os.getenv('PGDATABASE5') # Raw Data database
    DEMO_SU = os.getenv('DEMO_SU') # SU database
    
    BUS_SCHEDULE_FILE = os.getenv('BUS_SCHEDULE_FILE') # Handle Bus Schedule cases
    STARTING_TIME_FILE = os.getenv('STARTING_TIME_FILE') # Handle Bus Schedule cases
