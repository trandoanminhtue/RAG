from app.database.connection import get_db
from config import BUCKET_NAME

def update_status_DB(document_id: str, file_name: str, file_size_bytes: int):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents (
                id,
                file_name,
                file_size_bytes,
                minio_bucket,
                status
            )
            VALUES (%s, %s, %s, %s, 'PENDING')
            ON CONFLICT (id)
            DO UPDATE SET
                status = 'PENDING',
                updated_at = CURRENT_TIMESTAMP;
            """,
            (
                document_id,
                file_name,
                file_size_bytes,
                BUCKET_NAME,
            ),
        )
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()

    print(
        f"Document {document_id} "
        f"is PENDING"
    )