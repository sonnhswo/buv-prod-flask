import uuid
from flask import Blueprint, request, jsonify
from sqlalchemy import create_engine
from flasgger import swag_from

from app.chatbot import clear_history
from app.chatbot import generate_response
from app.db_models.raw_db import ChatSession, Chatbot, ChatMessage
from app.extensions import db
from config import Config

config = Config()
# Create a session
session = db.session

chatbot_blueprint = Blueprint('chatbot', __name__)
question_suggest_blueprint = Blueprint('question_suggest', __name__)

@chatbot_blueprint.route('/list', methods=['GET'])
def get_chatbots():
    """
    Get list of all chatbots with their details.
    ---
    responses:
      200:
        description: List of chatbots retrieved successfully
        schema:
          type: object
          properties:
            chatbots:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  name:
                    type: string
                  description:
                    type: string
                  database_name:
                    type: string
                  is_active:
                    type: boolean
                  publish_date:
                    type: string
                    format: date-time
                  created_at:
                    type: string
                    format: date-time
    """
    chatbots = Chatbot.query.all()
    chatbot_list = []

    for chatbot in chatbots:
        chatbot_data = {
            "id": chatbot.id,
            "name": chatbot.name,
            "description": chatbot.description,
            "database_name": chatbot.database_name,
            "is_active": chatbot.is_active,
            "publish_date": chatbot.publish_date.isoformat() if chatbot.publish_date else None,
            "created_at": chatbot.created_at.isoformat() if chatbot.created_at else None
        }

        # Add full name from config if available
        if chatbot.name in config.AB_CONFIGS:
            chatbot_data["full_name"] = config.AB_CONFIGS[chatbot.name].get("full_name")

        chatbot_list.append(chatbot_data)

    return jsonify({"chatbots": chatbot_list}), 200

@chatbot_blueprint.route('/<string:chatbot_name>/new_session_id', methods=['GET'])
def get_new_session_id(chatbot_name):
    """
    Get a new session ID for a chatbot.
    ---
    parameters:
      - name: chatbot_name
        in: path
        type: string
        required: true
        description: The name of the chatbot
    responses:
      200:
        description: New session created successfully
        schema:
          type: object
          properties:
            message:
              type: string
            data:
              type: object
              properties:
                session_id:
                  type: integer
    """
    chatbot = Chatbot.query.filter_by(name=chatbot_name).first()
    new_record = ChatSession(user_id=None, chatbot_id=chatbot.id)
    session.add(new_record)
    session.commit()
    session_id = new_record.id
    session.close()
    return jsonify({"message": "New chat session created successfully", "data": {"session_id": session_id}}), 200


@chatbot_blueprint.route('/clear_conversation', methods=['POST'])
def clear_conversation():
    """
    Clear the conversation history for a session.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            session_id:
              type: integer
              description: The session ID to clear
    responses:
      200:
        description: Conversation cleared
    """
    data: dict = request.json
    session_id: int = data.get('session_id')
    clear_history(str(session_id))
    return jsonify({"response": "Conversation cleared!"})


@chatbot_blueprint.route('/<string:awarding_body>', methods=['POST'])
def chat(awarding_body: str):
    """
    Send a message to the chatbot and get a response.
    ---
    parameters:
      - name: awarding_body
        in: path
        type: string
        required: true
        description: The awarding body (e.g., buv, su)
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            message:
              type: string
              description: The user's message
            session_id:
              type: integer
              description: The session ID
    responses:
      200:
        description: Chat response
        schema:
          type: object
          properties:
            answer:
              type: string
            source:
              type: string
            page_number:
              type: integer
            relevant_questions:
              type: array
              items:
                type: string
            ai_message_id:
              type: integer
      400:
        description: No message provided
      404:
        description: Awarding body not found
    """
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
    """
    Like a message.
    ---
    parameters:
      - name: message_id
        in: path
        type: integer
        required: true
        description: The ID of the message to like
    responses:
      200:
        description: Message liked successfully
      404:
        description: Message not found
    """
    message = ChatMessage.query.get(message_id)
    if message:
        message.like = config.THUMB_UP_VALUE
        session.commit()
        return jsonify({"message": "message liked successfully"}), 200
    else:
        return jsonify({"error": "Message not found"}), 404

@chatbot_blueprint.route('/dislike/<int:message_id>', methods=['GET'])
def thumb_down(message_id: int):
    """
    Dislike a message.
    ---
    parameters:
      - name: message_id
        in: path
        type: integer
        required: true
        description: The ID of the message to dislike
    responses:
      200:
        description: Message disliked successfully
      404:
        description: Message not found
    """
    message = ChatMessage.query.get(message_id)
    if message:
        message.like = config.THUMB_DOWN_VALUE
        session.commit()
        return jsonify({"message": "message disliked successfully"}), 200
    else:
        return jsonify({"error": "Message not found"}), 404 

@chatbot_blueprint.route('/unlike/<int:message_id>', methods=['GET'])
def no_thumb(message_id: int):
    """
    Remove like/dislike from a message.
    ---
    parameters:
      - name: message_id
        in: path
        type: integer
        required: true
        description: The ID of the message to unlike
    responses:
      200:
        description: Message unliked successfully
      404:
        description: Message not found
    """
    message = ChatMessage.query.get(message_id)
    if message:
        message.like = config.NO_THUMB_VALUE
        session.commit()
        return jsonify({"message": "message unliked successfully"}), 200
    else:
        return jsonify({"error": "Message not found"}), 404 

@question_suggest_blueprint.route('/start', methods=['GET'])
def start_questions():
    """
    Get suggested questions for an awarding body.
    ---
    parameters:
      - name: awarding_body
        in: query
        type: string
        required: true
        description: The awarding body (buv or su)
    responses:
      200:
        description: List of relevant questions
        schema:
          type: object
          properties:
            relevant_questions:
              type: array
              items:
                type: string
    """
    awarding_body = request.args.get("awarding_body")
    if awarding_body == "buv":
        chatbot = Chatbot.query.filter_by(name='buv').first()
    elif awarding_body == "su":
        chatbot = Chatbot.query.filter_by(name='su').first()
    else:
        return jsonify({'error': 'Invalid awarding body'}), 400
    
    if not chatbot:
        return jsonify({'error': 'Chatbot not found'}), 404

    results = [
        "How can I book an appointment with a tutor for academic support?",
        "What steps should I take if I am unable to attend an exam due to unforeseen circumstances?",
        "How can I access career counselling or job placement services at BUV?",
    ]
    
    return jsonify({'relevant_questions': results})