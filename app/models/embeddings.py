from dotenv import load_dotenv, find_dotenv
from langchain_openai import AzureOpenAIEmbeddings

from config import Config

load_dotenv(find_dotenv("../.env"), override=True)

config = Config()

# text_embedding_3large = AzureOpenAIEmbeddings(
#     model=config.AZURE_EMBEDDING_MODEL_DEPLOYMENT_NAME,
#     openai_api_version=config.AZURE_EMBEDDING_MODEL_OPENAI_VERSION,
#     openai_api_key=config.AZURE_OPENAI_API_KEY,
#     azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
# )
text_embedding_3large = AzureOpenAIEmbeddings(
    model="Embedding_Models",
    openai_api_version="2022-12-01",
    openai_api_key="68cd88ec2e0c4564a56a6ca13fc98a68",
    azure_endpoint="https://sio-bus-prod.openai.azure.com/",
)


