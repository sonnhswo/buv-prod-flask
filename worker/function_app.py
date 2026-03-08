import azure.functions as func
import logging
import json
import base64
import sys
import os

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.document_ingestion import process_file_ingestion
from app.db_models.raw_db import IngestionTask, Chatbot
from app.extensions import db

app = func.FunctionApp()

@app.queue_trigger(arg_name="azqueue", queue_name="document-ingestion-queue", connection="AzureWebJobsStorage") 
def ingest_document_queue_trigger(azqueue: func.QueueMessage):
    # Base64 decode the payload
    try:
        msg_body = azqueue.get_body().decode('utf-8')
        payload = json.loads(msg_body)
    except Exception as e:
        decoded = base64.b64decode(azqueue.get_body()).decode('utf-8')
        payload = json.loads(decoded)

    task_id = payload.get("task_id")
    chatbot_id = payload.get("chatbot_id")
    document_id = payload.get("document_id")
    document_type = payload.get("document_type")
    document_name = payload.get("document_name")
    document_path = payload.get("document_path")

    logging.info(f"Processing ingestion task {task_id} for file {document_name}")

    try:
        # We need an application context to interact with SQLAlchemy
        from manage import app as flask_app
        with flask_app.app_context():
            # Update status to PROCESSING
            task = db.session.get(IngestionTask, task_id)
            if task:
                task.status = 'PROCESSING'
                db.session.commit()
            
            # Since process_file_ingestion needs chatbot.name, we query it
            chatbot = db.session.get(Chatbot, chatbot_id)
            if not chatbot:
                raise Exception(f"Chatbot {chatbot_id} not found")

            # Execute the heavy ingestion pipeline
            process_file_ingestion(
                chatbot_id=str(chatbot_id),
                chatbot_name=chatbot.name,
                document_type=document_type,
                document_title=document_name,
                document_path=document_path
            )

            # Update status to COMPLETED
            if task:
                task = db.session.get(IngestionTask, task_id)
                task.status = 'COMPLETED'
                db.session.commit()
                logging.info(f"Successfully completed ingestion task {task_id}")

    except Exception as e:
        logging.error(f"Failed to process ingestion task {task_id}. Error: {str(e)}")
        # Try to mark the task as failed in the database
        try:
            from manage import app as flask_app
            with flask_app.app_context():
                task = db.session.get(IngestionTask, task_id)
                if task:
                    task.status = 'FAILED'
                    task.error_message = str(e)
                    db.session.commit()
        except:
            pass
        # Re-raise so Azure Functions knows it failed and can retry if configured
        raise e