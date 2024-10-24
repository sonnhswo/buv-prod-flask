import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')  # PostgreSQL URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AZURE_API_KEY = os.getenv('AZURE_API_KEY')
    AZURE_CHAT_MODEL = os.getenv('AZURE_CHAT_MODEL')
    AZURE_EMBEDDING_MODEL = os.getenv('AZURE_EMBEDDING_MODEL')
