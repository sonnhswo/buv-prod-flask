import uuid
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context, redirect, send_file
from sqlalchemy import create_engine
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import pandas as pd
from io import BytesIO

import os
from werkzeug.utils import secure_filename
from app.chatbot import clear_history
from app.chatbot import generate_response
from app.db_models.raw_db import ChatSession, Chatbot, ChatMessage, Document
from app.extensions import db
from config import Config
from app.auth import token_required
from .database import uni_dbs

config = Config()
# Create a session
session = db.session

chatbot_blueprint = Blueprint('chatbot', __name__)
question_suggest_blueprint = Blueprint('question_suggest', __name__)
user_portal_blueprint = Blueprint('user_portal', __name__)

# Azure Blob Storage Helper Functions
blob_service_client = BlobServiceClient.from_connection_string(config.BLOB_CONN_STRING)
container_name = config.BLOB_CONTAINER

@chatbot_blueprint.route('/<string:chatbot_id>/new_session_id', methods=['GET'])
def get_new_session_id(chatbot_id: str):
    # Check if chatbot exists
    chatbot = Chatbot.query.get(chatbot_id)
    if not chatbot:
        return jsonify({"error": "Chatbot not found"}), 404
    new_record = ChatSession(user_id="0", chatbot_id=chatbot_id)
    session.add(new_record)
    session.commit()
    session_id = new_record.id
    session.close()
    return jsonify({"message": "New chat session created successfully", "data": {"session_id": session_id}}), 200

def upload_blob(file, blob_path):
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
        blob_client.upload_blob(file, overwrite=True)
        return True
    except Exception as e:
        print(f"Error uploading blob: {e}")
        return False

def delete_blob(blob_path):
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
        if blob_client.exists():
            blob_client.delete_blob()
    except Exception as e:
        print(f"Error deleting blob: {e}")

def get_sas_url(blob_path):
    sas_token = generate_blob_sas(
        account_name=blob_service_client.account_name,
        container_name=container_name,
        blob_name=blob_path,
        account_key=blob_service_client.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=1)
    )
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
    return f"{blob_client.url}?{sas_token}"

@chatbot_blueprint.route('/clear_conversation', methods=['POST'])
def clear_conversation():
    data: dict = request.json
    session_id: int = data.get('session_id')
    clear_history(str(session_id))
    return jsonify({"response": "Conversation cleared!"})


@chatbot_blueprint.route('/<int:chatbot_id>', methods=['POST'])
def chat(chatbot_id: int):
    data: dict = request.json
    user_input: str = data.get('message')
    session_id: int = data.get('session_id')

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    if not session_id:
        return jsonify({"error": "No session_id provided"}), 400
    
    chatbot = Chatbot.query.get(chatbot_id)
    if not chatbot:
        return jsonify({"error": "Chatbot not found"}), 404

    ab_configs = config.AB_CONFIGS[chatbot.configuration['endpoint']]
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
        
    new_human_message = ChatMessage(message=user_input, is_user_message=True, session_id=session_id)
    new_ai_message = ChatMessage(message=response["answer"], is_user_message=False, session_id=session_id)
    session.add(new_human_message)
    session.add(new_ai_message)
    session.commit()
    response["ai_message_id"] = new_ai_message.id
    session.close()
    return jsonify(response)


@chatbot_blueprint.route('/<int:chatbot_id>/stream', methods=['POST'])
def chat_stream(chatbot_id: int):
    data: dict = request.json
    user_input: str = data.get('message')
    session_id: int = data.get('session_id')

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    if not session_id:
        return jsonify({"error": "No session_id provided"}), 400
    
    chatbot = Chatbot.query.get(chatbot_id)
    if not chatbot:
        return jsonify({"error": "Chatbot not found"}), 404

    ab_configs = config.AB_CONFIGS[chatbot.configuration['endpoint']]
    except_keywords = ab_configs['except_keywords']
    full_name = ab_configs['full_name']

    def generate():
        ask_relevant_question = True
        for keyword in except_keywords:
            if keyword in user_input:
                answer = f"Thank you for your question. Unfortunately, I can only provide answers related to {full_name}. Please reach out to our Student Information Office at studentservice@buv.edu.vn for further assistance."
                
                # Stream the static response
                yield f"data: {json.dumps({'type': 'content', 'content': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'metadata', 'source': None, 'page_number': None})}\n\n"
                yield f"data: {json.dumps({'type': 'questions', 'relevant_questions': []})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
                # Save to database
                new_human_message = ChatMessage(message=user_input, is_user_message=True, session_id=session_id)
                new_ai_message = ChatMessage(message=answer, is_user_message=False, session_id=session_id)
                session.add(new_human_message)
                session.add(new_ai_message)
                session.commit()
                
                yield f"data: {json.dumps({'type': 'message_id', 'ai_message_id': new_ai_message.id})}\n\n"
                
                ask_relevant_question = False
                return
        
        if ask_relevant_question:
            from app.chatbot import generate_response_stream
            full_answer = ""
            
            try:
                for chunk in generate_response_stream(user_input, str(session_id), full_name):
                    if chunk['type'] == 'content':
                        full_answer += chunk['content']
                    yield f"data: {json.dumps(chunk)}\n\n"
                
                # Save to database after streaming completes
                new_human_message = ChatMessage(message=user_input, is_user_message=True, session_id=session_id)
                new_ai_message = ChatMessage(message=full_answer, is_user_message=False, session_id=session_id)
                session.add(new_human_message)
                session.add(new_ai_message)
                session.commit()
                
                # Send message ID
                yield f"data: {json.dumps({'type': 'message_id', 'ai_message_id': new_ai_message.id})}\n\n"
                
            except Exception as e:
                print(f"Error during streaming: {e}")
                error_msg = "An error occurred while processing your request."
                yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


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
@token_required
def get_chatbots(current_user):
    query = Chatbot.query
    if current_user.division:
        query = query.filter((Chatbot.division == current_user.division) | (Chatbot.division.is_(None)))

    bots = query.order_by(Chatbot.created_at.desc()).all()
    return jsonify([{
        "id": f"CB{b.id:03d}",
        "name": b.name,
        "description": b.description or "",
        "publishDate": b.publish_date.strftime("%d/%m/%Y") if b.publish_date else "",
        "createdAt": b.created_at.strftime("%d/%m/%Y") if b.created_at else "",
        "lastModified": b.updated_at.strftime("%I:%M %p %d/%m/%Y") if b.updated_at else "",
        "status": "Active" if b.is_active else "Inactive"
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
        "publishDate": b.publish_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if b.publish_date else "",
        "createdAt": b.created_at.strftime("%d/%m/%Y") if b.created_at else "",
        "lastModified": b.updated_at.strftime("%I:%M %p %d/%m/%Y") if b.updated_at else "",
        "status": "Active" if b.is_active else "Inactive"
    })

@chatbot_blueprint.route('/api/chatbots', methods=['POST'])
@token_required
def create_chatbot(current_user):
    data = request.json
    new_bot = Chatbot(
        name=data.get('name'),
        description=data.get('description'),
        publish_date=datetime.fromisoformat(data.get('schedulePublish').replace('Z', '+00:00')) if data.get('schedulePublish') else None,
        is_active=True if data.get('status') == 'Active' else False,
        division=current_user.division
    )
    session.add(new_bot)
    session.commit()
    return jsonify({"message": "Created", "id": f"CB{new_bot.id:03d}"}), 201

@chatbot_blueprint.route('/api/chatbots/<string:id>', methods=['PUT'])
@token_required
def update_chatbot(current_user, id):
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

    if data.get('status'):
        bot.is_active = True if data.get('status') == 'Active' else False

    session.commit()
    return jsonify({"message": "Updated"}), 200

@chatbot_blueprint.route('/api/chatbots/<string:id>/files', methods=['GET'])
def get_chatbot_files(id):
    # TODO: Document table is still being updated in the database.
    return jsonify([])
    # db_id = int(id[2:]) if id.startswith("CB") else int(id)
    # # Adapted for uat_phase2 Document model (KNOWLEDGE_BASE)
    # files = Document.query.filter_by(chatbot_id=db_id, document_type='KNOWLEDGE_BASE').all()
    # return jsonify([{
    #     "id": str(f.id),
    #     "filename": f.name,
    #     "size": f.file_size,
    #     "created_at": f.created_at.isoformat() if f.created_at else ""
    # } for f in files])

@chatbot_blueprint.route('/api/chatbots/<string:id>/files', methods=['POST'])
@token_required
def upload_chatbot_file(current_user, id):
    # TODO: Document table is still being updated in the database.
    return jsonify({"error": "Feature unavailable"}), 503
    # db_id = int(id[2:]) if id.startswith("CB") else int(id)
    # chatbot = Chatbot.query.get(db_id)
    # if not chatbot:
    #     return jsonify({"error": "Chatbot not found"}), 404
    #
    # # Count existing KNOWLEDGE_BASE documents
    # existing_count = Document.query.filter_by(chatbot_id=db_id, document_type='KNOWLEDGE_BASE').count()
    # if existing_count >= 10:
    #     return jsonify({"error": "Max 10 files allowed"}), 400
    #
    # if 'file' not in request.files:
    #     return jsonify({"error": "No file part"}), 400
    #
    # file = request.files['file']
    # if file.filename == '':
    #     return jsonify({"error": "No selected file"}), 400
    #
    # file.seek(0, os.SEEK_END)
    # size = file.tell()
    # file.seek(0)
    #
    # if size > 5 * 1024 * 1024:
    #     return jsonify({"error": "File larger than 5MB"}), 400
    #
    # filename = secure_filename(file.filename)
    #
    # blob_path = f"chatbots/{db_id}/files/{filename}"
    # upload_blob(file, blob_path)
    #
    # # Adapt to Document model
    # new_file = Document(
    #     name=filename, 
    #     file_size=size, 
    #     chatbot_id=db_id, 
    #     document_type='KNOWLEDGE_BASE',
    #     file_path=blob_path
    # )
    # session.add(new_file)
    # session.commit()
    #
    # return jsonify({"id": str(new_file.id), "filename": filename}), 201

@chatbot_blueprint.route('/api/chatbots/<string:id>/files/<int:file_id>', methods=['DELETE'])
def delete_chatbot_file(id, file_id):
    # TODO: Document table is still being updated in the database.
    return jsonify({"error": "Feature unavailable"}), 503
    # db_id = int(id[2:]) if id.startswith("CB") else int(id)
    # file = Document.query.filter_by(id=file_id, chatbot_id=db_id).first()
    # if not file:
    #     return jsonify({"error": "File not found"}), 404
    # if file.file_path:
    #     delete_blob(file.file_path)
    # session.delete(file)
    # session.commit()
    # return jsonify({"message": "Deleted"}), 200

@chatbot_blueprint.route('/api/chatbots/<string:id>/files/<int:file_id>', methods=['PUT'])
def replace_chatbot_file(id, file_id):
    # TODO: Document table is still being updated in the database.
    return jsonify({"error": "Feature unavailable"}), 503
    # db_id = int(id[2:]) if id.startswith("CB") else int(id)
    # file_record = Document.query.filter_by(id=file_id, chatbot_id=db_id).first()
    # if not file_record:
    #     return jsonify({"error": "File not found"}), 404
    #
    # if 'file' not in request.files:
    #     return jsonify({"error": "No file part"}), 400
    #
    # file = request.files['file']
    # filename = secure_filename(file.filename)
    #
    # if file_record.file_path:
    #     delete_blob(file_record.file_path)
    #
    # blob_path = f"chatbots/{int(id[2:]) if id.startswith('CB') else int(id)}/files/{filename}"
    # upload_blob(file, blob_path)
    #
    # file_record.name = filename
    # file_record.file_path = blob_path
    # session.commit()
    # return jsonify({"message": "Updated"}), 200

@chatbot_blueprint.route('/api/chatbots/<string:id>/files/<int:file_id>/download', methods=['GET'])
def download_chatbot_file(id, file_id):
    # TODO: Document table is still being updated in the database.
    return jsonify({"error": "Feature unavailable"}), 404
    # file = Document.query.get(file_id)
    # if file and file.file_path:
    #     return redirect(get_sas_url(file.file_path))
    # return jsonify({"error": "File not found"}), 404

@chatbot_blueprint.route('/api/chatbots/<string:id>/status', methods=['PATCH'])
@token_required
def update_chatbot_status(current_user, id):
    db_id = int(id[2:]) if id.startswith("CB") else int(id)
    bot = Chatbot.query.get(db_id)
    if not bot:
        return jsonify({"error": "Not found"}), 404
    data = request.json
    # Adapted to uat_phase2 is_active field
    bot.is_active = True if data.get('status') == 'Active' else False
    if bot.is_active:
        bot.publish_date = datetime.now()
    else:
        bot.publish_date = None
    session.commit()
    return jsonify({"message": "Status updated"}), 200

@chatbot_blueprint.route('/api/chatbots/<string:id>/qna', methods=['GET'])
def get_chatbot_qna_files(id):
    # TODO: Document table is still being updated in the database.
    return jsonify([])
    # db_id = int(id[2:]) if id.startswith("CB") else int(id)
    # # Adapted for uat_phase2 Document model (QNA)
    # files = Document.query.filter_by(chatbot_id=db_id, document_type='QNA').order_by(Document.updated_at.desc()).all()
    # return jsonify([{
    #     "id": str(f.id),
    #     "name": f.name,
    #     "lastUpdate": f.updated_at.strftime("%I:%M %p %d/%m/%Y") if f.updated_at else ""
    # } for f in files])

@chatbot_blueprint.route('/api/chatbots/<string:id>/qna', methods=['POST'])
@token_required
def add_chatbot_qna_file(current_user, id):
    # TODO: Document table is still being updated in the database.
    return jsonify({"error": "Feature unavailable"}), 503
    # db_id = int(id[2:]) if id.startswith("CB") else int(id)
    # if 'file' not in request.files:
    #     return jsonify({"error": "No file part"}), 400
    # file = request.files['file']
    # if file.filename == '':
    #     return jsonify({"error": "No selected file"}), 400
    #
    # filename = secure_filename(file.filename)
    # blob_path = f"chatbots/{db_id}/qna/{filename}"
    # upload_blob(file, blob_path)
    #
    # # Adapt to Document model
    # new_file = Document(name=filename, chatbot_id=db_id, document_type='QNA', file_path=blob_path)
    # session.add(new_file)
    # session.commit()
    # return jsonify({"message": "File added"}), 201

@chatbot_blueprint.route('/api/chatbots/<string:id>/qna/<int:file_id>', methods=['DELETE'])
def delete_chatbot_qna_file(id, file_id):
    # TODO: Document table is still being updated in the database.
    return jsonify({"error": "Feature unavailable"}), 503
    # db_id = int(id[2:]) if id.startswith("CB") else int(id)
    # file = Document.query.filter_by(id=file_id, chatbot_id=db_id, document_type='QNA').first()
    # if not file:
    #     return jsonify({"error": "File not found"}), 404
    # if file.file_path:
    #     delete_blob(file.file_path)
    # session.delete(file)
    # session.commit()
    # return jsonify({"message": "Deleted"}), 200

@chatbot_blueprint.route('/api/chatbots/<string:id>/qna/<int:file_id>/download', methods=['GET'])
def download_chatbot_qna_file(id, file_id):
    # TODO: Document table is still being updated in the database.
    return jsonify({"error": "Feature unavailable"}), 404
    # db_id = int(id[2:]) if id.startswith("CB") else int(id)
    # file = Document.query.filter_by(id=file_id, chatbot_id=db_id, document_type='QNA').first()
    # if file and file.file_path:
    #     return redirect(get_sas_url(file.file_path))
    # return jsonify({"error": "File not found"}), 404

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


# User Portal Endpoints
@user_portal_blueprint.route('/chatbots/<string:division>', methods=['GET'])
def get_chatbots_by_division(division):
    """Get list of all active chatbots for a specific division"""
    try:
        chatbots = Chatbot.query.filter_by(division=division, is_active=True).all()
        
        chatbot_list = []
        for chatbot in chatbots:
            chatbot_list.append({
                'id': chatbot.id,
                'name': chatbot.name,
                'description': chatbot.description,
                'division': chatbot.division,
                'configuration': chatbot.configuration,
                'publish_date': chatbot.publish_date.isoformat() if chatbot.publish_date else None,
                'created_at': chatbot.created_at.isoformat() if chatbot.created_at else None,
                'updated_at': chatbot.updated_at.isoformat() if chatbot.updated_at else None
            })
        
        return jsonify({
            'data': chatbot_list,
            'count': len(chatbot_list)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@user_portal_blueprint.route('/chatbots/<int:chatbot_id>', methods=['GET'])
def get_chatbot_detail(chatbot_id):
    """Get detailed information about a specific chatbot"""
    try:
        chatbot = Chatbot.query.get(chatbot_id)
        
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404
        
        if not chatbot.is_active:
            return jsonify({'error': 'Chatbot is not active'}), 403
        
        chatbot_detail = {
            'id': chatbot.id,
            'name': chatbot.name,
            'description': chatbot.description,
            'database_name': chatbot.database_name,
            'attachments': chatbot.attachments,
            'configuration': chatbot.configuration,
            'division': chatbot.division,
            'is_active': chatbot.is_active,
            'publish_date': chatbot.publish_date.isoformat() if chatbot.publish_date else None,
            'created_at': chatbot.created_at.isoformat() if chatbot.created_at else None,
            'updated_at': chatbot.updated_at.isoformat() if chatbot.updated_at else None
        }
        
        return jsonify({
            'data': chatbot_detail
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@chatbot_blueprint.route('/api/logs/export', methods=['GET'])
@token_required
def export_logs(current_user):
    chatbot_id = request.args.get('chatbot_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    try:
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    except Exception:
        return jsonify({"error": "Invalid date format"}), 400

    query = session.query(ChatMessage, ChatSession, Chatbot)\
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)\
        .join(Chatbot, ChatSession.chatbot_id == Chatbot.id)\
        .filter(ChatMessage.created_at >= start_dt)\
        .filter(ChatMessage.created_at <= end_dt)

    if current_user.division:
        query = query.filter((Chatbot.division == current_user.division) | (Chatbot.division.is_(None)))

    if chatbot_id and chatbot_id.lower() != 'all':
        try:
            cid = int(chatbot_id[2:]) if chatbot_id.startswith("CB") else int(chatbot_id)
            query = query.filter(Chatbot.id == cid)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid chatbot_id format"}), 400

    query = query.order_by(ChatSession.id, ChatMessage.created_at)
    messages = query.all()

    rows = []
    pending = None

    for msg, sess, bot in messages:
        if pending and pending['session_id'] != sess.id:
            rows.append({
                "Question": pending['msg'].message, "Answer": "", "Thumb up/thumb down": 0,
                "Chatbot name": pending['bot_name'], "Timestamp": pending['msg'].created_at.strftime("%H:%M:%S %d-%m-%Y")
            })
            pending = None

        if msg.is_user_message:
            if pending:
                rows.append({
                    "Question": pending['msg'].message, "Answer": "", "Thumb up/thumb down": 0,
                    "Chatbot name": pending['bot_name'], "Timestamp": pending['msg'].created_at.strftime("%H:%M:%S %d-%m-%Y")
                })
            pending = {'msg': msg, 'session_id': sess.id, 'bot_name': bot.name}
        else:
            if pending:
                rows.append({
                    "Question": pending['msg'].message, "Answer": msg.message, "Thumb up/thumb down": msg.like or 0,
                    "Chatbot name": pending['bot_name'], "Timestamp": pending['msg'].created_at.strftime("%H:%M:%S %d-%m-%Y")
                })
                pending = None

    if pending:
        rows.append({
            "Question": pending['msg'].message, "Answer": "", "Thumb up/thumb down": 0,
            "Chatbot name": pending['bot_name'], "Timestamp": pending['msg'].created_at.strftime("%H:%M:%S %d-%m-%Y")
        })

    df = pd.DataFrame(rows)
    columns = ['Question', 'Answer', 'Thumb up/thumb down', 'Timestamp']
    if not chatbot_id or chatbot_id.lower() == 'all':
        columns.insert(3, 'Chatbot name')

    df = df[columns] if not df.empty else pd.DataFrame(columns=columns)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)

    return send_file(output, download_name="chatlog.xlsx", as_attachment=True)
