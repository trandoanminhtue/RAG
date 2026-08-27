from io import BytesIO
from minio import Minio
from config import MINIO_HOST, MINIO_PORT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, BUCKET_NAME

minio_client = Minio(
    endpoint=f"{MINIO_HOST}:{MINIO_PORT}",
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

def init_minio_bucket():
    if not minio_client.bucket_exists(BUCKET_NAME):
        minio_client.make_bucket(BUCKET_NAME)
    print(f"✅ kết nối thành công minIO; bucket: {BUCKET_NAME}")

def upload_minIO(document_id: str, file_size: int, content: bytes):
    print(f"[DEBUG] file_size nhận được: {file_size}")
    print(f"[DEBUG] Bắt đầu put_object...")
    minio_client.put_object(
        bucket_name=BUCKET_NAME,
        object_name=document_id,
        data=BytesIO(content),
        length=file_size,
        content_type="application/pdf",
    )
    print(f"[DEBUG] put_object hoàn tất")
    print(
        f"Upload completed: "
        f"{document_id} -> MinIO/{BUCKET_NAME}"
    )