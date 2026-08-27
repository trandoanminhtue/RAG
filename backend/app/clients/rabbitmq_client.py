import pika
import json
from config import RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASS, QUEUE_NAME

credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
parameters = pika.ConnectionParameters(
    host=RABBITMQ_HOST,
    port=RABBITMQ_PORT,
    credentials=credentials
)

def init_rabbit():
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    print(f"✅ Kết nối thành công rabbitMQ; Queue: '{QUEUE_NAME}'")
    connection.close()

def send_mes(document_id: str):
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=document_id.encode("utf-8"),
        properties=pika.BasicProperties(
            delivery_mode=2,
        ),
    )
    print(f"✅ Đã gửi task '{document_id}' vào queue '{QUEUE_NAME}'")
    connection.close()