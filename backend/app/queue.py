import base64
import json
import logging

import pika

from .config import settings

logger = logging.getLogger(__name__)

RABBITMQ_URL = settings.RABBITMQ_URL
QUEUE_NAME = settings.QUEUE_NAME


def publish_job(
    document_id: str,
    storage_key: str,
    user_id: int,
    file_bytes: bytes | None = None,
) -> None:
    """Publish a PDF processing job to RabbitMQ.

    If file_bytes is provided, the raw PDF is base64-encoded and included
    in the message so the worker can handle the MinIO upload.
    """
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)

        payload = {
            "document_id": document_id,
            "storage_key": storage_key,
            "user_id": str(user_id),
        }
        if file_bytes is not None:
            payload["file_b64"] = base64.b64encode(file_bytes).decode()

        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2),  # persistent
        )
        logger.info("Published job: doc=%s user=%s", document_id, user_id)
    finally:
        connection.close()
