from dotenv import load_dotenv, find_dotenv
from langchain_openai import AzureOpenAIEmbeddings

from config import Config

load_dotenv(find_dotenv("../.env"))

config = Config()

text_embedding_3large = AzureOpenAIEmbeddings(
    model=config.AZURE_EMBEDDING_MODEL_DEPLOYMENT_NAME,
    openai_api_version=config.AZURE_EMBEDDING_MODEL_OPENAI_VERSION,
    openai_api_key=config.AZURE_OPENAI_API_KEY,
    azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
)


