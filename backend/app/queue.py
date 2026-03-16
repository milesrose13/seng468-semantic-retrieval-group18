import json

import pika

from .config import settings

RABBITMQ_URL = settings.RABBITMQ_URL
QUEUE_NAME = settings.QUEUE_NAME


def publish_job(document_id: str, storage_key: str, user_id: int) -> None:
    """Publish a PDF processing job to RabbitMQ."""
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps(
                {
                    "document_id": document_id,
                    "storage_key": storage_key,
                    "user_id": str(user_id),
                }
            ),
            properties=pika.BasicProperties(delivery_mode=2),  # persistent
        )
    finally:
        connection.close()
