from dotenv import load_dotenv, find_dotenv
from langchain_openai import AzureChatOpenAI

from config import Config


load_dotenv(find_dotenv("../.env"))

config = Config()

azure_openai = AzureChatOpenAI(
    openai_api_version=config.AZURE_CHAT_MODEL_OPENAI_VERSION,
    azure_deployment=config.AZURE_DEPLOYMENT_NAME,
    temperature=0
)