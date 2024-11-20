import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(".env"), override=True)

class Config:
    
    AZURE_OPENAI_API_KEY = os.getenv('AZURE_OPENAI_API_KEY')
    print(f"{AZURE_OPENAI_API_KEY = }")
    AZURE_OPENAI_ENDPOINT = os.getenv('AZURE_OPENAI_ENDPOINT')
    print(f"{AZURE_OPENAI_ENDPOINT = }")
    AZURE_CHAT_MODEL_DEPLOYMENT_NAME = os.getenv('AZURE_CHAT_MODEL_DEPLOYMENT_NAME')
    print(f"{AZURE_CHAT_MODEL_DEPLOYMENT_NAME = }")
    AZURE_CHAT_MODEL_OPENAI_VERSION = os.getenv('AZURE_CHAT_MODEL_OPENAI_VERSION')
    print(f"{AZURE_CHAT_MODEL_OPENAI_VERSION = }")
    AZURE_EMBEDDING_MODEL_DEPLOYMENT_NAME = os.getenv('AZURE_EMBEDDING_MODEL_DEPLOYMENT_NAME')
    print(f"{AZURE_EMBEDDING_MODEL_DEPLOYMENT_NAME = }")
    AZURE_EMBEDDING_MODEL_OPENAI_VERSION = os.getenv('AZURE_EMBEDDING_MODEL_OPENAI_VERSION')
    print(f"{AZURE_EMBEDDING_MODEL_OPENAI_VERSION = }")
    
    BLOB_CONN_STRING = os.getenv('BLOB_CONN_STRING')
    BLOB_CONTAINER = os.getenv('BLOB_CONTAINER')
    
    COLLECTION_NAME = os.getenv('COLLECTION_NAME')
    
    PG_VECTOR_HOST = os.getenv('PG_VECTOR_HOST')
    PG_VECTOR_USER = os.getenv('PG_VECTOR_USER')
    PG_VECTOR_PASSWORD = os.getenv('PG_VECTOR_PASSWORD')
    PGPORT = os.getenv('PGPORT')
    
    PGDATABASE = os.getenv('PGDATABASE') # BUV database
    print(f"{PGDATABASE = }")
    PGDATABASE2 = os.getenv('PGDATABASE2') # Bus Schedule database
    print(f"{PGDATABASE2 = }")
    PGDATABASE3 = os.getenv('PGDATABASE3') # Bus General Info database
    print(f"{PGDATABASE3 = }")
    PGDATABASE4 = os.getenv('PGDATABASE4') # Unclear Questions database
    print(f"{PGDATABASE4 = }")
    PGDATABASE5 = os.getenv('PGDATABASE5') # Raw Data database
    print(f"{PGDATABASE5 = }")
    DEMO_SU = os.getenv('DEMO_SU') # SU database
    print(f"{DEMO_SU = }")
    
    BUS_SCHEDULE_FILE = os.getenv('BUS_SCHEDULE_FILE') # Handle Bus Schedule cases
    print(f"{BUS_SCHEDULE_FILE = }")
    STARTING_TIME_FILE = os.getenv('STARTING_TIME_FILE') # Handle Bus Schedule cases
    print(f"{STARTING_TIME_FILE = }")

    SQLALCHEMY_DATABASE_URI = f'postgresql://{PG_VECTOR_USER}:{PG_VECTOR_PASSWORD}@{PG_VECTOR_HOST}/{PGDATABASE5}'
