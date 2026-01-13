import uuid
from flask import Blueprint, request, jsonify
from sqlalchemy import create_engine
from datetime import datetime

import os
from werkzeug.utils import secure_filename
from app.chatbot import clear_history
from app.chatbot import generate_response
from app.db_models.raw_db import ChatSession, Chatbot, ChatMessage, QnAFile, ChatbotFile
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

@chatbot_blueprint.route('/api/chatbots', methods=['GET'])
def get_chatbots():
    bots = Chatbot.query.order_by(Chatbot.created_at.desc()).all()
    return jsonify([{
        "id": f"CB{b.id:03d}",
        "name": b.name,
        "description": b.description or "",
        "publishDate": b.publish_date.strftime("%d/%m/%Y") if b.publish_date else "",
        "createdAt": b.created_at.strftime("%d/%m/%Y") if b.created_at else "",
        "lastModified": b.last_modified.strftime("%I:%M %p %d/%m/%Y") if b.last_modified else "",
        "status": b.status
    } for b in bots])

@chatbot_blueprint.route('/api/chatbots/<string:id>', methods=['GET'])
def get_chatbot(id):
    # Strip CB prefix if present
    db_id = int(id[2:]) if id.startswith("CB") else int(id)
    b = Chatbot.query.get(db_id)
    if not b:
        return jsonify({"error": "Chatbot not found"}), 404
    return jsonify({
        "id": f"CB{b.id:03d}",
        "name": b.name,
        "description": b.description or "",
        "publishDate": b.publish_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if b.publish_date else "", # ISO format for form
        "createdAt": b.created_at.strftime("%d/%m/%Y") if b.created_at else "",
        "lastModified": b.last_modified.strftime("%I:%M %p %d/%m/%Y") if b.last_modified else "",
        "status": b.status
    })

@chatbot_blueprint.route('/api/chatbots', methods=['POST'])
def create_chatbot():
    data = request.json
    new_bot = Chatbot(
        name=data.get('name'),
        description=data.get('description'),
        publish_date=datetime.fromisoformat(data.get('schedulePublish').replace('Z', '+00:00')) if data.get('schedulePublish') else None,
        status='Active' if data.get('status') else 'Inactive'
    )
    session.add(new_bot)
    session.commit()
    return jsonify({"message": "Created", "id": f"CB{new_bot.id:03d}"}), 201

@chatbot_blueprint.route('/api/chatbots/<string:id>', methods=['PUT'])
def update_chatbot(id):
    db_id = int(id[2:]) if id.startswith("CB") else int(id)
    bot = Chatbot.query.get(db_id)
    if not bot:
        return jsonify({"error": "Not found"}), 404
    data = request.json
    bot.name = data.get('name', bot.name)
    bot.description = data.get('description', bot.description)
    if 'schedulePublish' in data:
        val = data.get('schedulePublish')
        bot.publish_date = datetime.fromisoformat(val.replace('Z', '+00:00')) if val else None
    bot.status = 'Active' if data.get('status') == 'Active' or data.get('status') is True else 'Inactive'
    session.commit()
    return jsonify({"message": "Updated"}), 200

@chatbot_blueprint.route('/api/chatbots/<string:id>/files', methods=['GET'])
def get_chatbot_files(id):
    db_id = int(id[2:]) if id.startswith("CB") else int(id)
    files = ChatbotFile.query.filter_by(chatbot_id=db_id).all()
    return jsonify([{
        "id": str(f.id),
        "filename": f.filename,
        "size": f.size,
        "created_at": f.created_at.isoformat()
    } for f in files])

@chatbot_blueprint.route('/api/chatbots/<string:id>/files', methods=['POST'])
def upload_chatbot_file(id):
    db_id = int(id[2:]) if id.startswith("CB") else int(id)
    chatbot = Chatbot.query.get(db_id)
    if not chatbot:
        return jsonify({"error": "Chatbot not found"}), 404

    if len(chatbot.files) >= 10:
        return jsonify({"error": "Max 10 files allowed"}), 400

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)

    if size > 5 * 1024 * 1024:
        return jsonify({"error": "File larger than 5MB"}), 400

    filename = secure_filename(file.filename)
    # In a real scenario, save to storage (blob/s3/local). 
    # Here we just record metadata to simulate upload success.

    new_file = ChatbotFile(filename=filename, size=size, chatbot_id=db_id)
    session.add(new_file)
    session.commit()

    return jsonify({"id": str(new_file.id), "filename": filename}), 201

@chatbot_blueprint.route('/api/chatbots/<string:id>/files/<int:file_id>', methods=['DELETE'])
def delete_chatbot_file(id, file_id):
    file = ChatbotFile.query.get(file_id)
    if file:
        session.delete(file)
        session.commit()
    return jsonify({"message": "Deleted"}), 200

@chatbot_blueprint.route('/api/chatbots/<string:id>/files/<int:file_id>', methods=['PUT'])
def replace_chatbot_file(id, file_id):
    file_record = ChatbotFile.query.get(file_id)
    if not file_record:
        return jsonify({"error": "File not found"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    file_record.filename = secure_filename(file.filename)
    # Update logic for size/content would go here
    session.commit()
    return jsonify({"message": "Updated"}), 200

@chatbot_blueprint.route('/api/chatbots/<string:id>/status', methods=['PATCH'])
def update_chatbot_status(id):
    db_id = int(id[2:]) if id.startswith("CB") else int(id)
    bot = Chatbot.query.get(db_id)
    if not bot:
        return jsonify({"error": "Not found"}), 404
    data = request.json
    bot.status = data.get('status')
    session.commit()
    return jsonify({"message": "Status updated"}), 200

@chatbot_blueprint.route('/api/chatbots/<string:id>/qna', methods=['GET'])
def get_chatbot_qna_files(id):
    db_id = int(id[2:]) if id.startswith("CB") else int(id)
    files = QnAFile.query.filter_by(chatbot_id=db_id).order_by(QnAFile.last_update.desc()).all()
    return jsonify([{
        "id": str(f.id),
        "name": f.name,
        "lastUpdate": f.last_update.strftime("%I:%M %p %d/%m/%Y")
    } for f in files])

@chatbot_blueprint.route('/api/chatbots/<string:id>/qna', methods=['POST'])
def add_chatbot_qna_file(id):
    db_id = int(id[2:]) if id.startswith("CB") else int(id)
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Simulate saving file (backend logic for XLSX processing would be here)
    filename = secure_filename(file.filename)
    new_file = QnAFile(name=filename, chatbot_id=db_id)
    session.add(new_file)
    session.commit()
    return jsonify({"message": "File added"}), 201

@chatbot_blueprint.route('/api/chatbots/<string:id>/qna/<int:file_id>', methods=['DELETE'])
def delete_chatbot_qna_file(id, file_id):
    file = QnAFile.query.get(file_id)
    if file:
        session.delete(file)
        session.commit()
    return jsonify({"message": "Deleted"}), 200

@chatbot_blueprint.route('/api/chatbots/<string:id>/qna/<int:file_id>/download', methods=['GET'])
def download_chatbot_qna_file(id, file_id):
    # Mock download
    return jsonify({"message": "File download simulation"}), 200

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