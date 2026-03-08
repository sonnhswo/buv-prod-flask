import base64
import json
import logging

import azure.functions as func

from ingestion.config import load_settings
from ingestion.db import DbClient
from ingestion.document_ingestion import IngestionRuntime, process_file_ingestion


app = func.FunctionApp()


def parse_queue_payload(msg: func.QueueMessage) -> dict:
    body = msg.get_body().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        decoded = base64.b64decode(msg.get_body()).decode("utf-8")
        return json.loads(decoded)


@app.queue_trigger(arg_name="azqueue", queue_name="document-ingestion-queue", connection="AzureWebJobsStorage")
def ingest_document_queue_trigger(azqueue: func.QueueMessage):
    payload = parse_queue_payload(azqueue)

    task_id = payload.get("task_id")
    chatbot_id = payload.get("chatbot_id")
    document_type = payload.get("document_type")
    document_name = payload.get("document_name")
    document_path = payload.get("document_path")

    logging.info("Processing ingestion task %s for file %s", task_id, document_name)

    settings = load_settings()
    db_client = DbClient(settings)

    try:
        db_client.set_task_processing(task_id)

        chatbot_name = db_client.get_chatbot_name(chatbot_id)
        if not chatbot_name:
            raise ValueError(f"Chatbot {chatbot_id} not found")

        runtime = IngestionRuntime(settings)
        process_file_ingestion(
            runtime=runtime,
            chatbot_id=str(chatbot_id),
            chatbot_name=chatbot_name,
            document_type=document_type,
            document_title=document_name,
            document_path=document_path,
        )

        db_client.set_task_completed(task_id)
        logging.info("Successfully completed ingestion task %s", task_id)

    except Exception as exc:
        logging.exception("Failed ingestion task %s", task_id)
        db_client.set_task_failed(task_id, str(exc))
        raise
