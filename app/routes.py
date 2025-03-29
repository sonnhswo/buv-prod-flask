import uuid
from flask import Blueprint, request, jsonify
from sqlalchemy import create_engine

from app.chatbot import clear_history
from app.chatbot import generate_response
from app.db_models.raw_db import ChatSession, Chatbot, ChatMessage
from app.extensions import db
from config import Config
from .database import uni_dbs

config = Config()
# Create a session
session = db.session

chatbot_blueprint = Blueprint('chatbot', __name__)
question_suggest_blueprint = Blueprint('question_suggest', __name__)

@chatbot_blueprint.route('/<string:chatbot_name>/new_session_id', methods=['GET'])
def get_new_session_id(chatbot_name):
    chatbot = Chatbot.query.filter_by(name=chatbot_name).first()
    new_record = ChatSession(user_id="0", chatbot_id=chatbot.id)
    session.add(new_record)
    session.commit()
    session_id = new_record.id
    session.close()
    return jsonify({"message": "New chat session created successfully", "data": {"session_id": session_id}}), 200


@chatbot_blueprint.route('/clear_conversation', methods=['POST'])
def clear_conversation():
    data: dict = request.json
    session_id: int = data.get('session_id')
    clear_history(str(session_id))
    return jsonify({"response": "Conversation cleared!"})


@chatbot_blueprint.route('/<string:awarding_body>', methods=['POST'])
def chat(awarding_body: str):
    data: dict = request.json
    user_input: str = data.get('message')
    session_id: int = data.get('session_id')
    print(f"{user_input = }")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    if not awarding_body in config.AB_CONFIGS.keys():
        return jsonify({"error": "Awarding_body not found"}), 404

    ab_configs = config.AB_CONFIGS[awarding_body]
    except_keywords = ab_configs['except_keywords']
    full_name = ab_configs['full_name']

    
    ask_relevant_question = True
    for keyword in except_keywords:
        if keyword in user_input:
            answer = f"Thank you for your question. Unfortunately, I can only provide answers related to {full_name}. Please reach out to our Student Information Office at studentservice@buv.edu.vn for further assistance."
            response = {
                "answer": answer,
                "source": None,
                "page_number": None,
                "relevant_questions": [] 
            }
            ask_relevant_question = False
            break
    
    if ask_relevant_question:
        response = generate_response(user_input, str(session_id), full_name)
        # print(f"{response=}")
        
    new_human_message = ChatMessage(message=user_input, is_user_message=True, session_id=session_id)
    new_ai_message = ChatMessage(message=response["answer"], is_user_message=False, session_id=session_id)
    session.add(new_human_message)
    session.add(new_ai_message)
    session.commit()
    response["ai_message_id"] = new_ai_message.id
    session.close()
    return jsonify(response)

@chatbot_blueprint.route('/like/<int:message_id>', methods=['GET'])
def thumb_up(message_id: int):
    message = ChatMessage.query.get(message_id)
    if message:
        message.like = config.THUMB_UP_VALUE
        session.commit()
        return jsonify({"message": "message liked successfully"}), 200
    else:
        return jsonify({"error": "Message not found"}), 404

@chatbot_blueprint.route('/dislike/<int:message_id>', methods=['GET'])
def thumb_down(message_id: int):
    message = ChatMessage.query.get(message_id)
    if message:
        message.like = config.THUMB_DOWN_VALUE
        session.commit()
        return jsonify({"message": "message disliked successfully"}), 200
    else:
        return jsonify({"error": "Message not found"}), 404 

@chatbot_blueprint.route('/unlike/<int:message_id>', methods=['GET'])
def no_thumb(message_id: int):
    message = ChatMessage.query.get(message_id)
    if message:
        message.like = config.NO_THUMB_VALUE
        session.commit()
        return jsonify({"message": "message unliked successfully"}), 200
    else:
        return jsonify({"error": "Message not found"}), 404 

@question_suggest_blueprint.route('/start', methods=['GET'])
def start_questions():
    awarding_body = request.args.get("awarding_body")
    if awarding_body == "buv":
        connection_string = uni_dbs['British University Vietnam']
    elif awarding_body == "su":
        connection_string = uni_dbs['Staffordshire University']

    results = [
        "How can I book an appointment with a tutor for academic support?",
        "What steps should I take if I am unable to attend an exam due to unforeseen circumstances?",
        "How can I access career counselling or job placement services at BUV?",
    ]
    
    return jsonify({'relevant_questions': results})