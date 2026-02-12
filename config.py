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

    DETERMINISTIC_TMP = int(os.getenv("DETERMINISTIC_TMP"))
    print(f"{DETERMINISTIC_TMP = }")
    CREATIVE_TMP = int(os.getenv("CREATIVE_TMP"))
    print(f"{CREATIVE_TMP = }")
    
    AZURE_INGEST_MODEL_DEPLOYMENT_NAME = os.getenv('AZURE_INGEST_MODEL_DEPLOYMENT_NAME')
    print(f"{AZURE_INGEST_MODEL_DEPLOYMENT_NAME = }")
    AZURE_INGEST_MODEL_DEPLOYMENT_VERSION = os.getenv('AZURE_INGEST_MODEL_DEPLOYMENT_VERSION')
    print(f"{AZURE_INGEST_MODEL_DEPLOYMENT_VERSION = }")

    DOC_INT_ENDPOINT = os.getenv("DOC_INT_ENDPOINT")
    print(f"{DOC_INT_ENDPOINT = }")
    DOC_INT_KEY = os.getenv("DOC_INT_KEY")
    print(f"{DOC_INT_KEY = }")

    AI_SEARCH_ENDPOINT = os.getenv("AI_SEARCH_ENDPOINT")
    print(f"{AI_SEARCH_ENDPOINT = }")
    INDEX_NAME = os.getenv("INDEX_NAME")
    print(f"{INDEX_NAME = }")
    PHASE1_INDEX_NAME = os.getenv("PHASE1_INDEX_NAME")
    print(f"{PHASE1_INDEX_NAME = }")
    AI_SEARCH_KEY = os.getenv("AI_SEARCH_KEY")
    print(f"{AI_SEARCH_KEY = }")
    VECTOR_SEARCH_PROFILE = os.getenv("VECTOR_SEARCH_PROFILE")
    print(f"{VECTOR_SEARCH_PROFILE = }")

    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE"))
    print(f"{CHUNK_SIZE = }")
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP"))
    print(f"{CHUNK_OVERLAP = }")

    DOC_TOP_K = int(os.getenv("DOC_TOP_K"))
    print(f"{DOC_TOP_K = }")
    QUESTION_TOP_K = int(os.getenv("QUESTION_TOP_K"))
    print(f"{QUESTION_TOP_K = }")
    FETCH_K = int(os.getenv("FETCH_K"))
    print(f"{FETCH_K = }")
    LAMBDA_MULT = float(os.getenv("LAMBDA_MULT"))
    print(f"{LAMBDA_MULT = }")

    STORAGE_URL = os.getenv("STORAGE_URL")
    print(f"{STORAGE_URL = }")
    CONTAINER_NAME = os.getenv("CONTAINER_NAME")
    print(f"{CONTAINER_NAME = }")
    STORAGE_KEY = os.getenv("STORAGE_KEY")
    print(f"{STORAGE_KEY = }")

    DOCX_TO_PDF_API_URL = os.getenv("DOCX_TO_PDF_API_URL")
    print(f"{DOCX_TO_PDF_API_URL = }")
    TIMEOUT = int(os.getenv("TIMEOUT"))
    print(f"{TIMEOUT = }")

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
    PGDATABASE6 = os.getenv('PGDATABASE6') # Raw Data database
    DEMO_SU = os.getenv('DEMO_SU') # SU database
    print(f"{DEMO_SU = }")
    PROD_UOL = os.getenv('DEMO_UOL') # UOL database
    print(f"{PROD_UOL = }")
    PROD_IFP = os.getenv('DEMO_IFP') # IFP database
    print(f"{PROD_IFP = }")
    PROD_AUB = os.getenv('DEMO_AUB') # AUB database
    print(f"{PROD_AUB = }")
    PROD_US = os.getenv('DEMO_US') # US database
    print(f"{PROD_US = }")
    
    BUS_SCHEDULE_FILE = os.getenv('BUS_SCHEDULE_FILE') # Handle Bus Schedule cases
    print(f"{BUS_SCHEDULE_FILE = }")
    STARTING_TIME_FILE = os.getenv('STARTING_TIME_FILE') # Handle Bus Schedule cases
    print(f"{STARTING_TIME_FILE = }")
    JWT_SECRET = os.getenv('JWT_SECRET')

    SQLALCHEMY_DATABASE_URI = f'postgresql://{PG_VECTOR_USER}:{PG_VECTOR_PASSWORD}@{PG_VECTOR_HOST}/{PGDATABASE6}'
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
    
    # CORS Configuration
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*').split(',')
    CORS_ALLOW_HEADERS = ['Content-Type', 'Authorization', 'X-Requested-With']
    CORS_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    CORS_SUPPORTS_CREDENTIALS = True
