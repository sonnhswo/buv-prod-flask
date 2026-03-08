import psycopg2
from psycopg2.extras import RealDictCursor

from .config import Settings


class DbClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    def _connect(self):
        return psycopg2.connect(
            host=self._settings.pg_host,
            user=self._settings.pg_user,
            password=self._settings.pg_password,
            port=self._settings.pg_port,
            dbname=self._settings.pg_database,
            sslmode="require",
        )

    def get_chatbot_name(self, chatbot_id: int) -> str | None:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT name FROM chatbot WHERE id = %s LIMIT 1", (chatbot_id,))
                row = cur.fetchone()
                return row["name"] if row else None

    def set_task_processing(self, task_id: int) -> None:
        self._set_task(task_id, "PROCESSING", None)

    def set_task_completed(self, task_id: int) -> None:
        self._set_task(task_id, "COMPLETED", None)

    def set_task_failed(self, task_id: int, message: str) -> None:
        self._set_task(task_id, "FAILED", message)

    def _set_task(self, task_id: int, status: str, error_message: str | None) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ingestion_task
                    SET status = %s,
                        error_message = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (status, error_message, task_id),
                )
                conn.commit()
