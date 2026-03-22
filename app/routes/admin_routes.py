import os
from io import BytesIO
from datetime import datetime, timezone, timedelta
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, redirect, send_file
import pandas as pd
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from app.storage import upload_blob, delete_blob, get_sas_url, enqueue_ingestion_task
from app.decorators import token_required
from app.db_models.raw_db import ChatSession, Chatbot, ChatMessage, Document, IngestionTask
from app.extensions import db
from app.database import delete_doc_from_kb, delete_qna
from app.routes.helpers import execute_safely, parse_chatbot_id

session = db.session

admin_portal_blueprint = Blueprint('admin_portal', __name__)


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
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    file = Document.query.filter_by(id=file_id, chatbot_id=db_id).first()
    tasks = IngestionTask.query.filter_by(document_id=file_id, chatbot_id=db_id).all()
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
        for t in tasks:
            session.delete(t)
        session.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        session.rollback()
        return jsonify({"error": f"Failed to delete file: {str(e)}"}), 500

@admin_portal_blueprint.route('/chatbots/<string:id>/files/<int:file_id>', methods=['PUT'])
@token_required
def replace_chatbot_file(current_user, id, file_id):
    try:
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
    except ValueError:
        return jsonify({"error": "Invalid chatbot identifier"}), 400

    chatbot = Chatbot.query.get(db_id)
    if not chatbot:
        return jsonify({"error": "Chatbot not found"}), 404

    status_filter = request.args.get("status")
    latest_per_file = request.args.get("latest_per_file", "true").lower() == "true"
    file_type = request.args.get("type")  # 'QNA' or 'KNOWLEDGE_BASE'

    query = IngestionTask.query.filter_by(chatbot_id=db_id)
    if status_filter:
        query = query.filter(IngestionTask.status == status_filter.upper())
    if file_type:
        query = query.join(Document).filter(Document.document_type == file_type)

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

    return jsonify({
        "chatbot_id": db_id,
        "latest_per_file": latest_per_file,
        "tasks": [serialize_task(task) for task in selected_tasks]
    }), 200


@admin_portal_blueprint.route('/chatbots/<string:id>/files/<int:file_id>/tasks', methods=['GET'])
@token_required
def get_file_ingestion_task_status(current_user, id, file_id):
    """Return latest ingestion task for a file, optionally with full history."""
    try:
        db_id = parse_chatbot_id(id)
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


@admin_portal_blueprint.route('/tasks/polling', methods=['GET'])
@token_required
def get_all_chatbots_ingestion_polling_map(current_user):
    """Return total and successful ingestion task counts per chatbot."""
    chatbot_query = Chatbot.query
    if current_user.division:
        chatbot_query = chatbot_query.filter((Chatbot.division == current_user.division) | (Chatbot.division.is_(None)))
    chatbots = chatbot_query.order_by(Chatbot.created_at.desc()).all()

    if not chatbots:
        return jsonify([]), 200

    bot_ids = [b.id for b in chatbots]
    task_counts = db.session.query(
        IngestionTask.chatbot_id,
        db.func.count(IngestionTask.id).label("total_tasks"),
        db.func.sum(db.case((IngestionTask.status == 'COMPLETED', 1), else_=0)).label("success_tasks")
    ).filter(
        IngestionTask.chatbot_id.in_(bot_ids)
    ).group_by(
        IngestionTask.chatbot_id
    ).all()
    task_counts_dict = {tc.chatbot_id: tc for tc in task_counts}

    return jsonify([{
        "chatbot_id": b.id,
        "total_tasks": task_counts_dict[b.id].total_tasks if b.id in task_counts_dict else 0,
        "success_tasks": task_counts_dict[b.id].success_tasks if b.id in task_counts_dict else 0
    } for b in chatbots]), 200

@admin_portal_blueprint.route('/chatbots/<string:id>/qna/<int:file_id>', methods=['DELETE'])
@token_required
def delete_chatbot_qna_file(current_user, id, file_id):
    try:
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
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
        db_id = parse_chatbot_id(id)
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
