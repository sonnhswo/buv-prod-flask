from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from openai import BadRequestError

from app.database import initialize_retrievers
from app.utils import language_detection_chain, add_prefix_to_answer
from app.chains import create_conversational_rag_chain, create_relevant_questions_chain, conversational_chain
from config import Config

config = Config()

doc_retrievers, question_retrievers = initialize_retrievers()

# Managing chat history
store = {}
def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()

    return store[session_id]

def trim_message_history(session_id: str):
    if session_id in store:
        store[session_id].messages = store[session_id].messages[-10:] if len(store[session_id].messages) > 10 else store[session_id].messages

def clear_history(session_id: str):
    if session_id in store:
        del store[session_id]

def generate_response(user_input: str, session_id: str, uni_name: str) -> str:
    try:
        language_detection = language_detection_chain.invoke({"input": user_input})
        print(f"{language_detection=}")
        if language_detection.strip().lower() == "vietnamese":
            answer = "We're sorry for any inconvenience; however, our chatbot can only answer questions in English. Unfortunately, Vietnamese isn't available at the moment. Thank you for your understanding!"
            source = None
            page_number = None
            relevant_questions = []
        else:
            # create history aware retriever
            doc_retriever = doc_retrievers[uni_name]
            question_retriever = question_retrievers[uni_name]
            
            conversational_rag_chain = create_conversational_rag_chain(doc_retriever, get_session_history)
            relevant_questions_chain = create_relevant_questions_chain(question_retriever)

            print(f"Before trimming {store=}")
            trim_message_history(session_id)
            print(f"After trimming {store=}")
            output = conversational_chain(conversational_rag_chain, relevant_questions_chain, user_input, session_id)
            
            answer = output.get("answer")
            source = output.get("source")
            page_number = output.get("page_number")
            relevant_questions = output.get("relevant_questions")

        return {
            "answer": add_prefix_to_answer(answer, uni_name),
            "source": source,
            "page_number": page_number,
            "relevant_questions": relevant_questions
        }
    
    except (BadRequestError, ValueError) as e:
        print(e)
        standard_message = "For further assistance, please contact our Student Information Office via email at studentservice@buv.edu.vn or by phone at 0936 376 136."
        
        return {
            "answer": add_prefix_to_answer(standard_message, uni_name),
            "source": None,
            "page_number": None,
            "relevant_questions": []
        }
    except Exception as e:
        print(e)
