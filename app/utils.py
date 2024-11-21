import re
from typing import Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from config import Config
from app.llm_models.chat_models import azure_openai

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

doc_options = ["BUV Frequently Asked Questions", "SU Frequently Asked Questions", "Student Handbook", "PSG Programme Handbook"]
class FormatedOutput(BaseModel):
    answer: str = Field(description="The answer to the user question")
    # source: Optional[Literal[*np.array(doc_options)]] = Field(description=f"Source document of the information retrieved, should be one of these options: {doc_options}") #type:ignore
    source: Optional[Literal["BUV Frequently Asked Questions", "SU Frequently Asked Questions", "Student Handbook", "PSG Programme Handbook"]] = Field(default=None, description=f"Source document of the information retrieved, should be one of these options: {doc_options}") #type:ignore
    page_number: Optional[str] = Field(default=None, description="The page number in the document where the information was retrieved")

def stringify_formatted_answer(inputs: FormatedOutput) -> str:
    return f"""
    Answer: {inputs.answer}\n\n
    Source: {inputs.source}\n\n
    Pages: {inputs.page_number}\n\n
    """

def extract_formatted_answer(stringify_answer):
    matches = re.search(r"Answer:\s*(.*?)\n\n\n\s*Source:\s*(.*?)\n\n\n\s*Pages:\s*(.*?)\n\n\n", stringify_answer, re.DOTALL)
    answer = matches.group(1).strip()
    source = matches.group(2).strip()
    page_number = matches.group(3).strip()
    blank_values = ["None", ""]
    if source in blank_values:
        source = None
    if page_number in blank_values:
        page_number = None

    print(f"{answer=}")
    print(f"{source=}")
    print(f"{page_number=}")
    return {
        "answer": answer,
        "source": source,
        "page_number": page_number,
    }

def add_prefix_to_answer(answer, uni_name):
    if uni_name == "British University Vietnam":
        return "**For BUV students:**\n\n" + answer
    
    if uni_name == "Staffordshire University":
        return "**For SU students:**\n\n" + answer
            
    return answer

class RelevantQuestionsOutput(BaseModel):
    questions: list[str] = Field(default=[], description="Relevant questions that the user may have regarding their conversation with the bot.")