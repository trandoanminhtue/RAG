import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, FastAPI

from app.clients.minio_client import upload_minIO
from app.services.document_service import update_status_DB
from app.clients.rabbitmq_client import send_mes
from config import BUCKET_NAME
from app.clients.minio_client import minio_client

router = APIRouter()

@router.post("/upload")
async def upload_doc(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF")

    content = await file.read()
    file_size = len(content)
    file_name = file.filename
    if file_size == 0:
        raise HTTPException(status_code=400, detail="File rỗng")

    document_id = str(uuid.uuid4())

    try:
        upload_minIO(document_id, file_size, content)
        minio_uploaded = True
        update_status_DB(document_id, file_name, file_size)
        send_mes(document_id)
    except Exception as e:
        if minio_uploaded:
            try:
                minio_client.remove_object(BUCKET_NAME, document_id)
                print(f"Rollback: Đã xóa dọn rác file {document_id} trên MinIO do DB lỗi.")
            except Exception as cleanup_error:
                print(f"Lỗi khi dọn rác MinIO: {cleanup_error}")
        raise HTTPException(status_code=500, detail=f"Upload thất bại: {e}")

    return {
        "success": True,
        "document_id": document_id,
        "file_name": file_name,
        "status": "PENDING",
        "message": f"Đã tải lên {file_name}, đang xử lý",
    }