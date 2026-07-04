import aio_pika
import json
import os
from typing import Any

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://pdfuser:pdfpass@localhost:5672/")

QUEUES = {
    "ocr":        "ocr_tasks",
    "ai_index":   "ai_index_tasks",
    "conversion": "conversion_tasks",
    "thumbnail":  "thumbnail_tasks",
    "signature":  "signature_tasks",
    "email":      "email_tasks",
}


async def get_connection() -> aio_pika.abc.AbstractConnection:
    return await aio_pika.connect_robust(RABBITMQ_URL)


async def publish(queue_name: str, payload: dict[str, Any]) -> None:
    connection = await get_connection()
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(queue_name, durable=True)
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=queue_name,
        )


async def consume(queue_name: str, callback) -> None:
    connection = await get_connection()
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(queue_name, durable=True)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process():
                payload = json.loads(message.body)
                await callback(payload)
