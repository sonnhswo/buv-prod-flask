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


class LanguageDetectionOutput(BaseModel):
    language: Literal["English", "Non_English"] = Field(
        description="The detected language of the text. 'English' if the text is in English, 'Non_English' for any other languages."
    )

language_detection_prompt_template = """
Identify whether the text below is in English or another language.

<text>
{input}
</text>
"""

language_detection_chain = (
    PromptTemplate.from_template(language_detection_prompt_template)
    | azure_openai.with_structured_output(LanguageDetectionOutput)
)

class FormatedOutput(BaseModel):
    answer: str = Field(
        description="The clean prose answer to the user question. DO NOT include titles, source names, or page numbers here."
    )
    source: Optional[str] = Field(
        default=None, 
        description="The EXACT File Name of the source document(s) (e.g., 'Assessment Approval Procedure Handbook - Sep 2024.pdf')"
    )
    page_number: Optional[str] = Field(
        default=None, 
        description="The page number(s) where the information was found. The page number MUST be selected from the specific context(s) used to write the answer. Do not include page number of irrelevant context."
    )

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
    
    if uni_name == "University of London":
        return "**For UoL students:**\n\n" + answer
    
    if uni_name == "International Foundation Programme":
        return "**For IFP students:**\n\n" + answer
    
    if uni_name == "Arts University Bournemouth":
        return "**For AUB students:**\n\n" + answer
    
    if uni_name == "University of Stirling":
        return "**For US students:**\n\n" + answer
            
    return answer
