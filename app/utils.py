from config import Config
from app.models.chat_models import azure_openai

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from sqlalchemy import create_engine, Column, Integer, Text, Table, MetaData
from sqlalchemy.ext.declarative import declarative_base

config = Config()

# def format_response(response):
#     # Utility function to format chatbot responses (e.g., for pretty-printing)
#     return response.strip()

# def handle_error(error):
#     # Utility function to handle errors
#     return {"error": str(error)}


language_detection_prompt_template = """
Identify the language of the text below as either `Vietnamese` or `Other`.

Respond with only one word.

<text>
{input}
</text>

Language:"""

language_detection_chain = (
    PromptTemplate.from_template(language_detection_prompt_template)
    | azure_openai
    | StrOutputParser()
)


# Create a base class using declarative_base
Base = declarative_base()

# Define your table as a model class
class FAQ(Base):
    __tablename__ = 'question_answer'  # Table name in the database

    id = Column(Integer, primary_key=True, autoincrement=True)  # Auto-incrementing primary key
    question = Column(Text, nullable=False)  # Question column of type text
    answer = Column(Text, nullable=False)  # Answer column of type text
    bot_type = Column(Text, nullable=False)  # Bot type column of type text




