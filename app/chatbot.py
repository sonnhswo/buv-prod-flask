import pprint

from app.models.chat_models import azure_openai
from app.database import initialize_retrievers
from app.utils import language_detection_chain

from langchain.prompts.chat import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain.chains.retrieval import create_retrieval_chain
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import AzureChatOpenAI


retrievers = initialize_retrievers()

# Managing chat history
store = {}
def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()

    return store[session_id]

def trim_message_history(session_id: str):
    if session_id in store:
        store[session_id].messages = store[session_id].messages[-10:] if len(store[session_id].messages) > 10 else store[session_id].messages


def generate_response(user_input: str, session_id: str, uni_name: str) -> str:
    language_detection = language_detection_chain.invoke({"input": user_input})
    print(f"{language_detection=}")
    if language_detection.strip().lower() == "vietnamese":
        answer = "We're sorry for any inconvenience; however, our chatbot can only answer questions in English. Unfortunately, Vietnamese isn't available at the moment. Thank you for your understanding!"
    else:
        
        # create contextualized prompt
        contextualized_system_prompt = (
            "Given a chat history and the latest user question "
            "which might reference context in the chat history, "
            "formulate a standalone question which can be understood "
            "without the chat history. Do NOT answer the question, "
            "just reformulate it if needed and otherwise return it as is."
        )
        
        contextualized_template = ChatPromptTemplate.from_messages(
            [
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                ("human", contextualized_system_prompt),
            ]
        )
        
        # create history aware retriever
        retriever = retrievers[uni_name]
        history_aware_retriever = create_history_aware_retriever(azure_openai, retriever, contextualized_template)
        
        # Create system prompt
        system_prompt_template = """
        As an AI assistant specializing in student support, your task is to provide concise and comprehensive answers to specific questions or inquiries based on the provided context.
        The context is a list of sources, each including the main information, the source name and its corresponding page number.
        You MUST follow the instructions inside the ###.

        ###
        Instructions:

        1. Read the context carefully.
        2. Only answer the question based on the information in the context.
        3. Keep your answer as succinct as possible, but ensure it includes all relevant information from the context. For example:
            - If students ask about a department or service, provide the department or service name, as well as the service link and department contact information such as email, phone, etc., if available in the context.
            - If the context does not have a specific answer but contains reference information such as a reference link, reference contact point, support contact point, etc., include that information.
            - If the context contains advice for specific student actions, include that advice.
        4. When you see the pattern \n in the context, it means a new line. With those texts that contain \n, you should read them carefully to understand the context.
        5. Use the word "documents" instead of "context" when referring to the provided information in the answer.
        6. The source names are provided right after the answer. Don't include the source names in the answer.
        7. Always include the title of the document from the context for each fact you use in the response in the following format:

        {{Answer here}}

        Sources:
        - Source Name 1 - Page <show page number here>
        - Source Name 2 - Page <show page number here>
        ...
        - Source Name n - Page <show page number here>

        8. If there are duplicate titles, only include that title once in the list of sources.
        9. You can only give the answer in British English style. For example, use "programme" instead of "program" or "organise" instead of "organize".
        10. If the history conversations contain useful information, you can respond based on the provided context and that information too. 
        11. If the provided context does not tell you the answer, please answer this template "Sorry, the documents do not mention about this information. Please contact the Student Information Office via studentservice@buv.edu.vn for further support.". After that, if there are any departments or guidance that can help. If the sources are empty strings " ", you can ignore them.
        ###

        --- Start Context:
        {context}
        --- End Context

        """
        
        system_template = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt_template),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}")
            ]
        )
        
        def create_stuff_documents_chain(llm: AzureChatOpenAI, 
                                        prompt: ChatPromptTemplate, 
                                        output_parser: StrOutputParser = StrOutputParser()):
            def format_docs(inputs: dict) -> str:
                formatted = []
                for i, doc in enumerate(inputs['context']):
                    doc_str = f"""Source Name: {doc.metadata['title']} - Page {doc.metadata['page_number']}\nInformation: {doc.page_content}"""
                    formatted.append(doc_str)
                return "\n\n".join(formatted)
                
            return (
                RunnablePassthrough.assign(**{"context": format_docs}).with_config(
                    run_name="format_inputs"
                )
                | prompt
                | llm
                | output_parser
                ).with_config(run_name="stuff_documents_chain")
        
        # create question answer chain rag chain
        question_answer_chain = create_stuff_documents_chain(azure_openai, system_template)
        rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain) #runnable
        
        
        conversational_rag_chain = RunnableWithMessageHistory(
            rag_chain, 
            get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="answer"
        )
        
        def conversational_chain(query: str, session_id: str) -> dict:
            print(f"{query=}")
            print(f"{session_id=}")
            answer = conversational_rag_chain.invoke(
                {"input": query},
                config={
                    "configurable": {"session_id": session_id}
                }
            )
            
            pprint.pprint(answer)
            return answer
        
        print(f"Before trimming {store=}")
        trim_message_history(session_id)
        response = conversational_chain(user_input, session_id)
        print(f"After trimming {store=}")
        
        answer = response["answer"]

    return answer
