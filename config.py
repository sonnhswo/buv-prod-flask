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
    
    # Vector database names for each chatbot (stored in DB, loaded here for seeding)
    PGDATABASE = os.getenv('PGDATABASE') # BUV database
    DEMO_SU = os.getenv('DEMO_SU') # SU database
    PROD_UOL = os.getenv('DEMO_UOL') # UOL database
    PROD_IFP = os.getenv('DEMO_IFP') # IFP database
    PROD_AUB = os.getenv('DEMO_AUB') # AUB database
    PROD_US = os.getenv('DEMO_US') # US database

    PGDATABASE_USER = os.getenv('PGDATABASE_USER')
    PGDATABASE_PASSWORD = os.getenv('PGDATABASE_PASSWORD')
    PGDATABASE_HOST = os.getenv('PGDATABASE_HOST')
    PGDATABASE_DB = os.getenv('PGDATABASE_DB')
    
    BUS_SCHEDULE_FILE = os.getenv('BUS_SCHEDULE_FILE') # Handle Bus Schedule cases
    print(f"{BUS_SCHEDULE_FILE = }")
    STARTING_TIME_FILE = os.getenv('STARTING_TIME_FILE') # Handle Bus Schedule cases
    print(f"{STARTING_TIME_FILE = }")

    SQLALCHEMY_DATABASE_URI = f'postgresql://{PGDATABASE_USER}:{PGDATABASE_PASSWORD}@{PGDATABASE_HOST}/{PGDATABASE_DB}'
    # configs for each awarding bodies
    AB_CONFIGS = {
        "buv": {
            "full_name": "British University Vietnam",
            "except_keywords": ["Stirling", "University of London", "UoL", "IFP", "Foundation", "Arts University Bournemouth", "Bournemouth", "AUB", "Staffordshire", "SU"]
        },
        "su": {
            "full_name": "Staffordshire University",
            "except_keywords": ["Stirling", "University of London", "UoL", "IFP", "Foundation", "Arts University Bournemouth", "Bournemouth", "AUB"]
        },
        "uol": {
            "full_name": "University of London",
            "except_keywords": ["Stirling", "IFP", "Foundation", "Arts University Bournemouth", "Bournemouth", "AUB", "Staffordshire", "SU"]
        },
        "ifp": {
            "full_name": "International Foundation Programme",
            "except_keywords": ["Stirling", "Arts University Bournemouth", "Bournemouth", "AUB", "Staffordshire", "SU"]
        },
        "aub": {
            "full_name": "Arts University Bournemouth",
            "except_keywords": ["Stirling", "University of London", "UoL", "IFP", "Foundation", "Staffordshire", "SU"]
        },
        "us": {
            "full_name": "University of Stirling",
            "except_keywords": ["University of London", "UoL", "IFP", "Foundation", "Staffordshire", "SU", "AUB", "Arts University Bournemouth"]
        }
    }
    THUMB_UP_VALUE = 1
    THUMB_DOWN_VALUE = -1
    NO_THUMB_VALUE = 0
