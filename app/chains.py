from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
import pprint

from app.llm_models.chat_models import azure_openai

from langchain.prompts.chat import ChatPromptTemplate
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain.chains.retrieval import create_retrieval_chain
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import AzureChatOpenAI

from .utils import FormatedOutput, RelevantQuestionsOutput, stringify_formatted_answer, extract_formatted_answer
from .prompt_templates import contextualized_template, system_template, relevant_question_template

def create_stuff_documents_chain(llm: AzureChatOpenAI, 
                                            prompt: ChatPromptTemplate, 
                                            output_parser: StrOutputParser = StrOutputParser()):
    def format_docs(inputs: dict) -> str:
        formatted = []
        for i, doc in enumerate(inputs['context']):
            doc_str = f"""Source Name: {doc.metadata['title']} - Page {doc.metadata['page_number']}\nInformation: {doc.page_content}"""
            formatted.append(doc_str)
        return "\n\n".join(formatted)
    print("abc")
    return (
        RunnablePassthrough.assign(**{"context": format_docs}).with_config(
            run_name="format_inputs"
        )
        | prompt
        | llm.with_structured_output(FormatedOutput)
        | stringify_formatted_answer
        ).with_config(run_name="stuff_documents_chain")


def create_conversational_rag_chain(retriever, get_session_history):
    history_aware_retriever = create_history_aware_retriever(azure_openai, retriever, contextualized_template)

    question_answer_chain = create_stuff_documents_chain(azure_openai, system_template)
    rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain) #runnable
    return RunnableWithMessageHistory(
            rag_chain, 
            get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="answer"
            )

def suggest_relevant_questions_chain(context, input, answer):
    chain = relevant_question_template | azure_openai.with_structured_output(RelevantQuestionsOutput)
    response = chain.invoke({"context": context, "input": input, "answer": answer})
    print("relevant questions:", response)
    return response
def conversational_chain(conversational_rag_chain, query: str, session_id: str) -> dict:
    print(f"{query=}")
    print(f"{session_id=}")
    response = conversational_rag_chain.invoke(
        {"input": query},
        config={
            "configurable": {"session_id": session_id}
        }
    )
    relevant_questions = suggest_relevant_questions_chain(response['context'], query, response['answer'])
    pprint.pprint(response)
    output = extract_formatted_answer(response['answer'])
    output['relevant_questions'] = relevant_questions.questions
    return output