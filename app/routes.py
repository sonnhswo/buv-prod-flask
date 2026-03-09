import uuid
import json
import os
import threading
import queue
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, Response, stream_with_context, redirect, send_file
from sqlalchemy import create_engine
from datetime import datetime, timezone, timedelta
import pandas as pd
from io import BytesIO
from app.chatbot import clear_history
from app.chatbot import generate_response
from app.storage import upload_blob, delete_blob, get_sas_url, enqueue_ingestion_task
from app.decorators import token_required
from app.document_ingestion import process_file_ingestion
from app.db_models.raw_db import ChatSession, Chatbot, ChatMessage, Document, IngestionTask
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from app.extensions import db
from config import Config
from app.database import delete_doc_from_kb, uni_dbs, delete_qna

config = Config()
# Create a session
session = db.session

chatbot_blueprint = Blueprint('chatbot', __name__)
question_suggest_blueprint = Blueprint('question_suggest', __name__)
user_portal_blueprint = Blueprint('user_portal', __name__)
admin_portal_blueprint = Blueprint('admin_portal', __name__)

@chatbot_blueprint.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200


def execute_safely(func, *args, **kwargs):
    q = queue.Queue()
    def wrapper():
        try:
            res = func(*args, **kwargs)
            q.put(("SUCCESS", res))
        except Exception as e:
            q.put(("ERROR", e))
    t = threading.Thread(target=wrapper)
    t.start()
    t.join()
    status, res = q.get()
    if status == "ERROR":
        raise res
    return res

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

    ab_configs = None
    if chatbot.configuration:
        ab_configs = config.AB_CONFIGS.get(chatbot.configuration['endpoint'])
    
    # phase 1 bots
    if ab_configs:
        except_keywords = ab_configs['except_keywords']
        full_name = ab_configs['full_name']
    # phase 2 bots
    else:
        except_keywords = []
        full_name = chatbot.name

    ask_relevant_question = True
    for keyword in except_keywords:
        if keyword.lower() in user_input.lower():
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
        print(f"Executing langchain for chatbot {full_name=}.")
        response = generate_response(user_input, str(session_id), str(chatbot.id), full_name)

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

    ab_configs = None
    if chatbot.configuration:
        ab_configs = config.AB_CONFIGS.get(chatbot.configuration['endpoint'])
    
    # phase 1 bots
    if ab_configs:
        except_keywords = ab_configs['except_keywords']
        full_name = ab_configs['full_name']
    # phase 2 bots
    else:
        except_keywords = []
        full_name = chatbot.name

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
                for chunk in generate_response_stream(user_input, str(session_id), str(chatbot.id), full_name):
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

@user_portal_blueprint.route('/chatbots/<int:chatbot_id>/files/<string:filename>/download', methods=['GET'])
def download_chatbot_file_by_name(chatbot_id, filename):
    file = Document.query.filter_by(name=filename, chatbot_id=chatbot_id).first()
    if not file:
        file = Document.query.filter_by(name=secure_filename(filename), chatbot_id=chatbot_id).first()
    if file and file.file_path:
        url = get_sas_url(file.file_path, filename=file.name)
        if url:
            return redirect(url)
    return jsonify({"error": "File not found"}), 404

# Admin Portal Endpoints

@admin_portal_blueprint.route('/chatbots', methods=['GET'])
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
        "publishDate": b.publish_date.isoformat() if b.publish_date else None,
        "createdAt": b.created_at.isoformat() if b.created_at else None,
        "lastModified": b.updated_at.isoformat() if b.updated_at else None,
        "status": "Active" if b.is_active else "Inactive"
    } for b in bots])

@admin_portal_blueprint.route('/chatbots/<string:id>', methods=['GET'])
@token_required
def get_admin_chatbot(current_user, id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400
    b = Chatbot.query.get(db_id)
    if not b:
        return jsonify({"error": "Chatbot not found"}), 404
    return jsonify({
        "id": f"CB{b.id:03d}",
        "name": b.name,
        "description": b.description or "",
        "publishDate": b.publish_date.isoformat() if b.publish_date else None,
        "createdAt": b.created_at.isoformat() if b.created_at else None,
        "lastModified": b.updated_at.isoformat() if b.updated_at else None,
        "status": "Active" if b.is_active else "Inactive"
    })

@admin_portal_blueprint.route('/chatbots', methods=['POST'])
@token_required
def create_chatbot(current_user):
    data = request.json
    try:
        publish_date = datetime.fromisoformat(data.get('schedulePublish').replace('Z', '+00:00')) if data.get('schedulePublish') else None
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400

    is_active = True if data.get('status') == 'Active' else False
    if publish_date and publish_date.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
        is_active = False

    new_bot = Chatbot(
        name=data.get('name'),
        description=data.get('description'),
        publish_date=publish_date,
        is_active=is_active,
        division=current_user.division
    )
    session.add(new_bot)
    session.commit()
    return jsonify({"message": "Created", "id": f"CB{new_bot.id:03d}"}), 201

@admin_portal_blueprint.route('/chatbots/<string:id>', methods=['PUT'])
@token_required
def update_chatbot(current_user, id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400
    bot = Chatbot.query.get(db_id)
    if not bot:
        return jsonify({"error": "Not found"}), 404
    data = request.json
    bot.name = data.get('name', bot.name)
    bot.description = data.get('description', bot.description)
    if 'schedulePublish' in data:
        val = data.get('schedulePublish')
        try:
            bot.publish_date = datetime.fromisoformat(val.replace('Z', '+00:00')) if val else None
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400

    if data.get('status'):
        bot.is_active = True if data.get('status') == 'Active' else False

    if bot.publish_date and bot.publish_date.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
        bot.is_active = False

    bot.updated_at = db.func.now()
    session.commit()
    return jsonify({"message": "Updated"}), 200

@admin_portal_blueprint.route('/chatbots/<string:id>/files', methods=['GET'])
@token_required
def get_chatbot_files(current_user, id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    files = Document.query.filter_by(chatbot_id=db_id, document_type='KNOWLEDGE_BASE').all()
    return jsonify([{
        "id": str(f.id),
        "filename": f.name,
        "size": f.file_size,
        "created_at": f.created_at.isoformat() if f.created_at else ""
    } for f in files])

@admin_portal_blueprint.route('/chatbots/<string:id>/files', methods=['POST'])
@token_required
def upload_chatbot_file(current_user, id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    chatbot = Chatbot.query.get(db_id)
    if not chatbot:
        return jsonify({"error": "Chatbot not found"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    # if file size is greater than 10MB, reject the upload

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > 10 * 1024 * 1024:
        return jsonify({"error": "Invalid file"}), 400

    filename = secure_filename(file.filename)

    existing_file = Document.query.filter_by(chatbot_id=db_id, name=filename).first()
    if existing_file:
        return jsonify({"error": f"A file named {filename} already existed"}), 400

    blob_path = f"chatbots/{db_id}/files/{filename}"

    if execute_safely(upload_blob, file, blob_path):
        new_file = Document(
            name=filename, 
            file_size=size, 
            chatbot_id=db_id, 
            document_type='KNOWLEDGE_BASE',
            file_path=blob_path,
            owner_id=current_user.id
        )
        session.add(new_file)
        session.flush() # flush to get the new_file.id

        new_task = IngestionTask(chatbot_id=db_id, document_id=new_file.id, status='PENDING')
        session.add(new_task)
        session.flush()
        session.commit()

        # Drop the task to Azure Storage Queue
        enqueued = enqueue_ingestion_task(
            task_id=new_task.id, 
            chatbot_id=db_id, 
            document_id=new_file.id, 
            document_type='KNOWLEDGE_BASE', 
            document_name=new_file.name, 
            document_path=new_file.file_path
        )
        
        if not enqueued:
            new_task.status = 'FAILED'
            new_task.error_message = 'Failed to enqueue task'
            session.commit()
            return jsonify({"error": "File saved but failed to queue for ingestion"}), 500

        return jsonify({
            "id": str(new_file.id), 
            "filename": filename, 
            "size": size, 
            "created_at": new_file.created_at.isoformat(),
            "task_id": new_task.id
        }), 202
    else:
        return jsonify({"error": "Failed to upload to storage"}), 500

@admin_portal_blueprint.route('/chatbots/<string:id>/files/<int:file_id>/ingest', methods=['POST'])
@token_required
def ingest_chatbot_file(current_user, id, file_id):
    """
    Ingests a specific file associated with a chatbot into the knowledge base.
    
    This endpoint triggers the data extraction and vectorization process for a given file.
    Depending on the `document_type` ('QNA' or 'KNOWLEDGE_BASE'), it uses the 
    appropriate ingestor (`QnAIngestor` or `DocumentIngestor`).

    Args:
        current_user: The authenticated user object (injected by @token_required).
        id (str): The chatbot identifier (e.g., 'CB001' or '1').
        file_id (int): The ID of the file to ingest in the database.

    Returns:
        tuple[Response, int]: A JSON response and HTTP status code indicating success or failure.
            - 200: Successfully ingested `{"message": "Ingested"}`.
            - 400: Bad request (invalid chatbot ID, empty name, or unsupported document type).
            - 404: File or Chatbot not found in the database.
            - 500: Server error during the ingestion process.
    """
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    file = Document.query.filter_by(id=file_id, chatbot_id=db_id).first()
    if not file:
        return jsonify({"error": "File not found"}), 404
    
    chatbot = Chatbot.query.filter_by(id=db_id).first()
    
    if not chatbot.name :
        return jsonify({"error": "Chatbot name empty"}), 400
    if file.document_type not in ['QNA','KNOWLEDGE_BASE'] :
        return jsonify({"error": "Unrecognized file document type"}), 400
    try:
        new_task = IngestionTask(chatbot_id=db_id, document_id=file.id, status='PENDING')
        session.add(new_task)
        session.commit()

        enqueued = enqueue_ingestion_task(
            task_id=new_task.id, 
            chatbot_id=db_id, 
            document_id=file.id, 
            document_type=file.document_type, 
            document_name=file.name, 
            document_path=file.file_path
        )

        if not enqueued:
            new_task.status = 'FAILED'
            new_task.error_message = 'Failed to enqueue task'
            session.commit()
            return jsonify({"error": "Failed to queue file for ingestion"}), 500

        return jsonify({"message": "Ingestion queued successfully", "task_id": new_task.id}), 202

    except Exception as e:
        return jsonify({"error": f"Failed to queue ingestion: \n\t{e}"}), 500

@admin_portal_blueprint.route('/chatbots/<string:id>/files/<int:file_id>', methods=['DELETE'])
@token_required
def delete_chatbot_file(current_user, id, file_id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    file = Document.query.filter_by(id=file_id, chatbot_id=db_id).first()
    if not file:
        return jsonify({"error": "File not found"}), 404

    chatbot = Chatbot.query.get(db_id)
    chatbot_name = chatbot.name if chatbot else None
    file_name = file.name

    try:
        if chatbot_name and file_name:
            res = execute_safely(delete_doc_from_kb, str(chatbot.id), chatbot_name, file_name)
            if res == -1:
                raise Exception("Failed to delete document from KB")
        if file.file_path:
            execute_safely(delete_blob, file.file_path)
        session.delete(file)
        session.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        session.rollback()
        return jsonify({"error": f"Failed to delete file: {str(e)}"}), 500

@admin_portal_blueprint.route('/chatbots/<string:id>/files/<int:file_id>', methods=['PUT'])
@token_required
def replace_chatbot_file(current_user, id, file_id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    file_record = Document.query.filter_by(id=file_id, chatbot_id=db_id).first()
    if not file_record:
        return jsonify({"error": "File not found"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)

    filename = secure_filename(file.filename)

    existing_file = Document.query.filter(Document.chatbot_id==db_id, Document.name==filename, Document.id!=file_id).first()
    if existing_file:
        return jsonify({"error": f"A file named {filename} already existed"}), 400

    chatbot = Chatbot.query.get(db_id)
    if chatbot and file_record.name:
        res = execute_safely(delete_doc_from_kb, str(chatbot.id), chatbot.name, file_record.name)
        if res == -1:
            return jsonify({"error": "Failed to delete old document from KB"}), 500

    if file_record.file_path:
        delete_blob(file_record.file_path)

    blob_path = f"chatbots/{db_id}/files/{filename}"
    if execute_safely(upload_blob, file, blob_path):
        file_record.name = filename
        file_record.file_path = blob_path
        file_record.file_size = size
        file_record.owner_id = current_user.id
        
        new_task = IngestionTask(chatbot_id=db_id, document_id=file_record.id, status='PENDING')
        session.add(new_task)
        session.commit()

        enqueued = enqueue_ingestion_task(
            task_id=new_task.id, 
            chatbot_id=db_id, 
            document_id=file_record.id, 
            document_type='KNOWLEDGE_BASE', 
            document_name=file_record.name, 
            document_path=file_record.file_path
        )
        
        if not enqueued:
            new_task.status = 'FAILED'
            new_task.error_message = 'Failed to enqueue task'
            session.commit()
            return jsonify({"error": "File replaced but failed to queue for ingestion"}), 500

        return jsonify({
            "id": str(file_record.id), 
            "filename": filename, 
            "size": size, 
            "created_at": file_record.created_at.isoformat(),
            "task_id": new_task.id
        }), 202
    else:
        return jsonify({"error": "Failed to upload to storage"}), 500

@admin_portal_blueprint.route('/chatbots/<string:id>/files/<int:file_id>/download', methods=['GET'])
def download_chatbot_file(id, file_id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    file = Document.query.filter_by(id=file_id, chatbot_id=db_id).first()
    if file and file.file_path:
        url = get_sas_url(file.file_path, filename=file.name)
        if url:
            return redirect(url)
    return jsonify({"error": "File not found"}), 404

@admin_portal_blueprint.route('/chatbots/<string:id>/qna', methods=['GET'])
@token_required
def get_chatbot_qna_files(current_user, id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    files = Document.query.filter_by(chatbot_id=db_id, document_type='QNA').order_by(Document.updated_at.desc()).all()
    return jsonify([{
        "id": str(f.id),
        "name": f.name,
        "lastUpdate": f.updated_at.isoformat() if f.updated_at else None
    } for f in files])

@admin_portal_blueprint.route('/chatbots/<string:id>/qna', methods=['POST'])
@token_required
def add_chatbot_qna_file(current_user, id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)

    existing_file = Document.query.filter_by(chatbot_id=db_id, name=filename).first()
    if existing_file:
        return jsonify({"error": f"A file named {filename} already existed"}), 400

    blob_path = f"chatbots/{db_id}/qna/{filename}"

    if execute_safely(upload_blob, file, blob_path):
        new_file = Document(name=filename, chatbot_id=db_id, document_type='QNA', file_path=blob_path, owner_id=current_user.id)
        session.add(new_file)
        session.flush()

        new_task = IngestionTask(chatbot_id=db_id, document_id=new_file.id, status='PENDING')
        session.add(new_task)
        session.commit()

        enqueued = enqueue_ingestion_task(
            task_id=new_task.id, 
            chatbot_id=db_id, 
            document_id=new_file.id, 
            document_type='QNA', 
            document_name=new_file.name, 
            document_path=new_file.file_path
        )

        if not enqueued:
            new_task.status = 'FAILED'
            new_task.error_message = 'Failed to enqueue task'
            session.commit()
            return jsonify({"error": "File added but failed to queue for ingestion"}), 500

        return jsonify({"message": "File added and ingestion queued", "task_id": new_task.id}), 202
    else:
        return jsonify({"error": "Failed to upload"}), 500

@admin_portal_blueprint.route('/chatbots/<string:id>/tasks/<int:task_id>', methods=['GET'])
@token_required
def get_ingestion_task_status(current_user, id, task_id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    task = IngestionTask.query.filter_by(id=task_id, chatbot_id=db_id).first()
    if not task:
        return jsonify({"error": "Task not found"}), 404

    return jsonify({
        "id": task.id,
        "chatbot_id": task.chatbot_id,
        "document_id": task.document_id,
        "status": task.status,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None
    }), 200


@admin_portal_blueprint.route('/chatbots/<string:id>/tasks', methods=['GET'])
@token_required
def get_chatbot_ingestion_tasks_status(current_user, id):
    """Return ingestion task status list for a chatbot."""
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    chatbot = Chatbot.query.get(db_id)
    if not chatbot:
        return jsonify({"error": "Chatbot not found"}), 404

    status_filter = request.args.get("status")
    latest_per_file = request.args.get("latest_per_file", "true").lower() == "true"

    query = IngestionTask.query.filter_by(chatbot_id=db_id)
    if status_filter:
        query = query.filter(IngestionTask.status == status_filter.upper())

    tasks = query.order_by(IngestionTask.created_at.desc()).all()

    def serialize_task(task):
        return {
            "id": task.id,
            "chatbot_id": task.chatbot_id,
            "document_id": task.document_id,
            "document_name": task.document.name if task.document else None,
            "status": task.status,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None
        }

    selected_tasks = tasks
    if latest_per_file:
        seen_document_ids = set()
        deduped = []
        for task in tasks:
            if task.document_id in seen_document_ids:
                continue
            seen_document_ids.add(task.document_id)
            deduped.append(task)
        selected_tasks = deduped

    counts = {"PENDING": 0, "PROCESSING": 0, "COMPLETED": 0, "FAILED": 0}
    for task in selected_tasks:
        if task.status in counts:
            counts[task.status] += 1

    return jsonify({
        "chatbot_id": db_id,
        "chatbot_name": chatbot.name,
        "latest_per_file": latest_per_file,
        "status_filter": status_filter.upper() if status_filter else None,
        "count": len(selected_tasks),
        "counts": counts,
        "tasks": [serialize_task(task) for task in selected_tasks]
    }), 200


@admin_portal_blueprint.route('/chatbots/<string:id>/files/<int:file_id>/tasks', methods=['GET'])
@token_required
def get_file_ingestion_task_status(current_user, id, file_id):
    """Return latest ingestion task for a file, optionally with full history."""
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    file = Document.query.filter_by(id=file_id, chatbot_id=db_id).first()
    if not file:
        return jsonify({"error": "File not found"}), 404

    tasks = IngestionTask.query.filter_by(chatbot_id=db_id, document_id=file_id)\
        .order_by(IngestionTask.created_at.desc())\
        .all()

    if not tasks:
        return jsonify({
            "file_id": file_id,
            "chatbot_id": db_id,
            "status": "NO_TASK",
            "task": None
        }), 200

    def serialize_task(task):
        return {
            "id": task.id,
            "chatbot_id": task.chatbot_id,
            "document_id": task.document_id,
            "status": task.status,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None
        }

    include_history = request.args.get("include_history", "false").lower() == "true"
    latest_task = tasks[0]

    payload = {
        "file_id": file_id,
        "chatbot_id": db_id,
        "status": latest_task.status,
        "task": serialize_task(latest_task)
    }

    if include_history:
        payload["tasks"] = [serialize_task(task) for task in tasks]

    return jsonify(payload), 200

@admin_portal_blueprint.route('/chatbots/<string:id>/qna/<int:file_id>', methods=['DELETE'])
@token_required
def delete_chatbot_qna_file(current_user, id, file_id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    file = Document.query.filter_by(id=file_id, chatbot_id=db_id, document_type='QNA').first()
    if not file:
        return jsonify({"error": "File not found"}), 404

    chatbot = Chatbot.query.get(db_id)
    chatbot_name = chatbot.name if chatbot else None
    file_name = file.name

    try:
        if chatbot_name and file_name:
            res = execute_safely(delete_qna, str(chatbot.id), chatbot_name, file_name)
            if res == -1:
                raise Exception("Failed to delete QnA from KB")
        if file.file_path:
            execute_safely(delete_blob, file.file_path)
        session.delete(file)
        session.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        session.rollback()
        return jsonify({"error": f"Failed to delete QnA file: {str(e)}"}), 500

@admin_portal_blueprint.route('/chatbots/<string:id>/qna/<int:file_id>/download', methods=['GET'])
def download_chatbot_qna_file(id, file_id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    file = Document.query.filter_by(id=file_id, chatbot_id=db_id, document_type='QNA').first()
    if file and file.file_path:
        url = get_sas_url(file.file_path, filename=file.name)
        if url:
            return redirect(url)
    return jsonify({"error": "File not found"}), 404

@admin_portal_blueprint.route('/chatbots/<string:id>/status', methods=['PATCH'])
@token_required
def update_chatbot_status(current_user, id):
    try:
        db_id = int(id[2:]) if id.startswith("CB") else int(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot id"}), 400
    bot = Chatbot.query.get(db_id)
    if not bot:
        return jsonify({"error": "Not found"}), 404
    data = request.json
    # Adapted to uat_phase2 is_active field
    bot.is_active = True if data.get('status') == 'Active' else False
    if bot.is_active:
        bot.publish_date = datetime.now(timezone.utc)
    else:
        bot.publish_date = None
    session.commit()
    return jsonify({"message": "Status updated"}), 200

@admin_portal_blueprint.route('/logs/export', methods=['GET'])
@token_required
def export_logs(current_user):
    chatbot_id = request.args.get('chatbot_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    tz_offset = request.args.get('tz_offset', default=0, type=int)

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
                "Chatbot name": pending['bot_name'], "Timestamp": (pending['msg'].created_at - timedelta(minutes=tz_offset)).strftime("%H:%M:%S %d-%m-%Y")
            })
            pending = None

        if msg.is_user_message:
            if pending:
                rows.append({
                    "Question": pending['msg'].message, "Answer": "", "Thumb up/thumb down": 0,
                    "Chatbot name": pending['bot_name'], "Timestamp": (pending['msg'].created_at - timedelta(minutes=tz_offset)).strftime("%H:%M:%S %d-%m-%Y")
                })
            pending = {'msg': msg, 'session_id': sess.id, 'bot_name': bot.name}
        else:
            if pending:
                rows.append({
                    "Question": pending['msg'].message, "Answer": msg.message, "Thumb up/thumb down": msg.like or 0,
                    "Chatbot name": pending['bot_name'], "Timestamp": (pending['msg'].created_at - timedelta(minutes=tz_offset)).strftime("%H:%M:%S %d-%m-%Y")
                })
                pending = None

    if pending:
        rows.append({
            "Question": pending['msg'].message, "Answer": "", "Thumb up/thumb down": 0,
            "Chatbot name": pending['bot_name'], "Timestamp": (pending['msg'].created_at - timedelta(minutes=tz_offset)).strftime("%H:%M:%S %d-%m-%Y")
        })

    df = pd.DataFrame(rows)
    columns = ['Question', 'Answer', 'Thumb up/thumb down', 'Timestamp']
    if not chatbot_id or chatbot_id.lower() == 'all':
        columns.insert(3, 'Chatbot name')

    df = df[columns] if not df.empty else pd.DataFrame(columns=columns)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Give the sheet a name so we can reference it easily
        sheet_name = 'Chat Logs'
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        
        # Access the openpyxl worksheet object
        worksheet = writer.sheets[sheet_name]
        
        # Iterate through the columns to apply formatting
        for idx, col in enumerate(df.columns):
            # Calculate the maximum length of the data in the column (or header)
            max_data_len = df[col].astype(str).map(len).max() if not df[col].empty else 0
            max_len = max(max_data_len, len(str(col)))
            
            # Set a max width cap (e.g., 50) so long messages wrap instead of stretching horizontally
            adjusted_width = min(max_len + 2, 50)
            
            # Get the column letter (A, B, C...)
            col_letter = get_column_letter(idx + 1)
            
            # 1. Set the column width
            worksheet.column_dimensions[col_letter].width = adjusted_width
            
            # 2. Enable text wrapping for all cells in this column so row heights scale automatically
            for row in range(1, len(df) + 2):  # +2 accounts for 1-based index and header row
                cell = worksheet[f"{col_letter}{row}"]
                cell.alignment = Alignment(wrap_text=True, vertical='top')

    output.seek(0)

    return send_file(output, download_name="chatlog.xlsx", as_attachment=True)
