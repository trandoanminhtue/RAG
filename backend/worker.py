from main import done_admin
import pika
from main import QUEUE_NAME
from main import parameters

def get_mes():
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.queue_declare(
        queue=QUEUE_NAME,
        durable=True
    )

    def callback(ch, method, properties, body):
        document_id = body.decode("utf-8")
        print(f"📥 Nhận task: {document_id}")

        try:
            done_admin(document_id)     
            ch.basic_ack(
            delivery_tag=method.delivery_tag
            )
            print(f"✅ Xử lý task {document_id} thành công")

        except Exception as e:
            print(f"❌ Xử lý task {document_id} thất bại: {e}")

    channel.basic_consume(
        queue=QUEUE_NAME,
        on_message_callback=callback
    )

    print(f"👂 Đang chờ message từ queue '{QUEUE_NAME}'...")

    channel.start_consuming()

if __name__ == "__main__":
    get_mes()