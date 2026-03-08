from datetime import datetime, timedelta, timezone
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from azure.storage.queue import QueueServiceClient
import base64
import json
from config import Config

config = Config()

# Azure Blob Storage Helper Functions
blob_service_client = None
queue_service_client = None
if config.BLOB_CONN_STRING:
    try:
        blob_service_client = BlobServiceClient.from_connection_string(config.BLOB_CONN_STRING)
        queue_service_client = QueueServiceClient.from_connection_string(config.BLOB_CONN_STRING)
        
        # Ensure the queue exists
        queue_client = queue_service_client.get_queue_client("document-ingestion-queue")
        try:
            queue_client.create_queue()
        except Exception:
            pass # Queue already exists
            
    except Exception as e:
        print(f"Failed to initialize Azure Storage Clients: {e}")
container_name = config.BLOB_CONTAINER

def upload_blob(file, blob_path):
    if blob_service_client is None:
        return False
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
        blob_client.upload_blob(file, overwrite=True)
        return True
    except Exception as e:
        print(f"Error uploading blob: {e}")
        return False

def delete_blob(blob_path):
    if blob_service_client is None:
        return
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
        if blob_client.exists():
            blob_client.delete_blob()
    except Exception as e:
        print(f"Error deleting blob: {e}")

def get_sas_url(blob_path, filename=None):
    if blob_service_client is None:
        return None
    try:
        kwargs = {}
        if filename:
            if filename.lower().endswith('.pdf'):
                kwargs['content_disposition'] = f'inline; filename="{filename}"'
                kwargs['content_type'] = 'application/pdf'
            else:
                kwargs['content_disposition'] = f'attachment; filename="{filename}"'

        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=container_name,
            blob_name=blob_path,
            account_key=blob_service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=1),
            **kwargs
        )
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
        return f"{blob_client.url}?{sas_token}"
    except Exception as e:
        print(f"Error generating SAS URL: {e}")
        return None

def enqueue_ingestion_task(task_id: int, chatbot_id: int, document_id: int, document_type: str, document_name: str, document_path: str):
    if queue_service_client is None:
        print("Queue service client not initialized.")
        return False
        
    try:
        queue_client = queue_service_client.get_queue_client("document-ingestion-queue")
        
        message_dict = {
            "task_id": task_id,
            "chatbot_id": chatbot_id,
            "document_id": document_id,
            "document_type": document_type,
            "document_name": document_name,
            "document_path": document_path
        }
        
        # Azure Storage expects base64 encoded strings
        message_b64 = base64.b64encode(json.dumps(message_dict).encode('utf-8')).decode('utf-8')
        queue_client.send_message(message_b64)
        print(f"Successfully enqueued task {task_id}")
        return True
    except Exception as e:
        print(f"Error enqueueing message: {e}")
        return False

