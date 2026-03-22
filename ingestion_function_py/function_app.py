import base64
import json
import logging
from time import perf_counter

import azure.functions as func

from ingestion.config import load_settings
from ingestion.db import DbClient
from ingestion.document_ingestion import IngestionRuntime, process_file_ingestion


app = func.FunctionApp()


def _log_step_start(step_name: str, **fields) -> float:
    field_str = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    logging.info("[STEP_START] %s %s", step_name, field_str)
    return perf_counter()


def _log_step_done(step_name: str, started_at: float, **fields) -> None:
    elapsed_ms = (perf_counter() - started_at) * 1000
    field_str = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    logging.info("[STEP_DONE] %s elapsed_ms=%.2f %s", step_name, elapsed_ms, field_str)


def parse_queue_payload(msg: func.QueueMessage) -> dict:
    body = msg.get_body().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        decoded = base64.b64decode(msg.get_body()).decode("utf-8")
        return json.loads(decoded)


@app.queue_trigger(arg_name="azqueue", queue_name="document-ingestion-queue", connection="AzureWebJobsStorage")
def ingest_document_queue_trigger(azqueue: func.QueueMessage):
    invocation_started = _log_step_start("ingest_document_queue_trigger")

    step_started = _log_step_start("parse_queue_payload")
    payload = parse_queue_payload(azqueue)
    _log_step_done("parse_queue_payload", step_started)

    task_id = payload.get("task_id")
    chatbot_id = payload.get("chatbot_id")
    document_type = payload.get("document_type")
    document_name = payload.get("document_name")
    document_path = payload.get("document_path")

    logging.info("Processing ingestion task %s for file %s", task_id, document_name)

    step_started = _log_step_start("load_settings", task_id=task_id)
    settings = load_settings()
    _log_step_done("load_settings", step_started)

    step_started = _log_step_start("init_db_client", task_id=task_id)
    db_client = DbClient(settings)
    _log_step_done("init_db_client", step_started)

    try:
        step_started = _log_step_start("set_task_processing", task_id=task_id)
        db_client.set_task_processing(task_id)
        _log_step_done("set_task_processing", step_started, task_id=task_id)

        step_started = _log_step_start("get_chatbot_name", chatbot_id=chatbot_id)
        chatbot_name = db_client.get_chatbot_name(chatbot_id)
        _log_step_done("get_chatbot_name", step_started, chatbot_name=chatbot_name)
        if not chatbot_name:
            raise ValueError(f"Chatbot {chatbot_id} not found")

        step_started = _log_step_start("init_ingestion_runtime", task_id=task_id)
        runtime = IngestionRuntime(settings)
        _log_step_done("init_ingestion_runtime", step_started)

        step_started = _log_step_start(
            "process_file_ingestion",
            task_id=task_id,
            chatbot_id=chatbot_id,
            document_type=document_type,
            document_name=document_name,
            document_path=document_path,
        )
        process_file_ingestion(
            runtime=runtime,
            chatbot_id=str(chatbot_id),
            chatbot_name=chatbot_name,
            document_type=document_type,
            document_title=document_name,
            document_path=document_path,
        )
        _log_step_done("process_file_ingestion", step_started, task_id=task_id)

        step_started = _log_step_start("set_task_completed", task_id=task_id)
        db_client.set_task_completed(task_id)
        _log_step_done("set_task_completed", step_started, task_id=task_id)

        _log_step_done("ingest_document_queue_trigger", invocation_started, task_id=task_id)
        logging.info("Successfully completed ingestion task %s", task_id)

    except Exception as exc:
        logging.exception("Failed ingestion task %s", task_id)
        step_started = _log_step_start("set_task_failed", task_id=task_id)
        db_client.set_task_failed(task_id, str(exc))
        _log_step_done("set_task_failed", step_started, task_id=task_id)
        raise
