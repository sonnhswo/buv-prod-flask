from dotenv import load_dotenv, find_dotenv
from langchain_openai import AzureChatOpenAI

from config import Config


load_dotenv(find_dotenv("../.env"), override=True)

config = Config()

# LLM for chat responses
azure_openai = AzureChatOpenAI(
    openai_api_version=config.AZURE_CHAT_MODEL_OPENAI_VERSION,
    azure_deployment=config.AZURE_CHAT_MODEL_DEPLOYMENT_NAME,
    temperature=0
)
# LLM for 1:1 reformatting (needs to be strict/precise)
llm_fixer = AzureChatOpenAI(
    openai_api_version = config.AZURE_INGEST_MODEL_DEPLOYMENT_VERSION,
    azure_deployment   = config.AZURE_INGEST_MODEL_DEPLOYMENT_NAME,
    api_key            = config.AZURE_OPENAI_API_KEY,
    temperature        = 0 # Deterministic
)
# LLM for creative question generation (needs variety)
llm_generator = AzureChatOpenAI(
    openai_api_version = config.AZURE_INGEST_MODEL_DEPLOYMENT_VERSION,
    azure_deployment   = config.AZURE_INGEST_MODEL_DEPLOYMENT_NAME,
    api_key            = config.AZURE_OPENAI_API_KEY,
    temperature        = 1.0 # Creative/Diverse
)