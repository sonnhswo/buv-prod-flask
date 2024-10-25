from config import Config
from app.models.chat_models import azure_openai

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser


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




