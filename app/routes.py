from flask import Blueprint, request, jsonify

from app.chatbot import clear_history
from app.chatbot import generate_response
from app.utils import FAQ
from config import Config

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

config = Config()

# Create an engine that connects to the PostgreSQL database
engine = create_engine(f"postgresql+psycopg://{config.PG_VECTOR_USER}:{config.PG_VECTOR_PASSWORD}@{config.PG_VECTOR_HOST}:{config.PGPORT}/{config.PGDATABASE5}")
# Create a configured "Session" class
Session = sessionmaker(bind=engine)
# Create a session
session = Session()


chatbot_blueprint = Blueprint('chatbot', __name__)

@chatbot_blueprint.route('/clear_conversation', methods=['POST'])
def clear_conversation():
    data: dict = request.json
    session_id: str = data.get('session_id')
    clear_history(session_id)
    return jsonify({"response": "Conversation cleared!"})


@chatbot_blueprint.route('/buv', methods=['POST'])
def buv_chat():
    data: dict = request.json
    user_input: str = data.get('message')
    session_id: str = data.get('session_id')
    print(f"{user_input = }")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    ask_relevant_question = True
    keywords = ["Stirling", "University of London", "UoL", "IFP", "Foundation", "Arts University Bournemouth", "Bournemouth", "AUB", "Staffordshire", "SU"]
    for keyword in keywords:
        if keyword in user_input:
            response = "Thank you for your question. Unfortunately, I can only provide answers related to British University Vietnam. Please reach out to our Student Information Office at studentservice@buv.edu.vn for further assistance."
            ask_relevant_question = False
            # Create a new FAQ instance
            new_faq = FAQ(question=user_input, answer=response, bot_type="British University Vietnam")
            # Add the new instance to the session
            session.add(new_faq)
            # Commit the session to insert the data into the table
            session.commit()
            session.close()
            break
    
    if ask_relevant_question:
        response = generate_response(user_input, str(session_id), "British University Vietnam")
        
    return jsonify(response)


@chatbot_blueprint.route('/su', methods=['POST'])
def su_chat():
    data: dict = request.json
    user_input: str = data.get('message')
    session_id: str = data.get('session_id')
    print(f"{user_input = }")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    ask_relevant_question = True
    keywords = ["Stirling", "University of London", "UoL", "IFP", "Foundation", "Arts University Bournemouth", "Bournemouth", "AUB", "Staffordshire"]
    for keyword in keywords:
        if keyword in user_input:
            response = "Thank you for your question. Unfortunately, I can only provide answers related to Staffordshire University. Please reach out to our Student Information Office at studentservice@buv.edu.vn for further assistance."
            ask_relevant_question = False
            # Create a new FAQ instance
            new_faq = FAQ(question=user_input, answer=response, bot_type="Staffordshire University")
            # Add the new instance to the session
            session.add(new_faq)
            # Commit the session to insert the data into the table
            session.commit()
            session.close()
            break
    
    if ask_relevant_question:
        response = generate_response(user_input, str(session_id), "Staffordshire University")
        
    return jsonify(response)
