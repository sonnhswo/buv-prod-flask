from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from openai import BadRequestError

from app.database import initialize_retrievers
from app.utils import language_detection_chain, FAQ, add_prefix_to_answer
from app.chains import create_conversational_rag_chain, conversational_chain
from config import Config



config = Config()

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

def clear_history(session_id: str):
    if session_id in store:
        del store[session_id]

# Create an engine that connects to the PostgreSQL database
engine = create_engine(f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PGDATABASE5}")
# Create a configured "Session" class
Session = sessionmaker(bind=engine)
# Create a session
session = Session()

def generate_response(user_input: str, session_id: str, uni_name: str) -> str:
    try:
        language_detection = language_detection_chain.invoke({"input": user_input})
        print(f"{language_detection=}")
        if language_detection.strip().lower() == "vietnamese":
            answer = "We're sorry for any inconvenience; however, our chatbot can only answer questions in English. Unfortunately, Vietnamese isn't available at the moment. Thank you for your understanding!"
            source = None
            page_number = None
        else:
            # create history aware retriever
            retriever = retrievers[uni_name]
            
            conversational_rag_chain = create_conversational_rag_chain(retriever, get_session_history)

            print(f"Before trimming {store=}")
            trim_message_history(session_id)
            print(f"After trimming {store=}")
            output = conversational_chain(conversational_rag_chain, user_input, session_id)
            
            answer = output.get("answer")
            source = output.get("source")
            page_number = output.get("page_number")

        # Save user_input and answer to question_answer table in the raw_data_users_20240826 database
        # Create a new FAQ instance
        new_faq = FAQ(question=user_input, answer=answer, bot_type=uni_name)
        # Add the new instance to the session
        session.add(new_faq)
        # Commit the session to insert the data into the table
        session.commit()
        
        return {
            "answer": add_prefix_to_answer(answer, uni_name),
            "source": source,
            "page_number": page_number,
        }
    
    except (BadRequestError, ValueError):
        standard_message = "For further assistance, please contact our Student Information Office via email at studentservice@buv.edu.vn or by phone at 0936 376 136."
        
        # Create a new FAQ instance
        new_faq = FAQ(question=user_input, answer=standard_message, bot_type=uni_name)
        # Add the new instance to the session
        session.add(new_faq)
        # Commit the session to insert the data into the table
        session.commit()
        
        return {
            "answer": add_prefix_to_answer(standard_message, uni_name),
            "source": None,
            "page_number": None,
        }
        
    finally:
        session.close()
