import psycopg2
from config import POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
from app.database.model import create_tables

def get_db():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    try:
        create_tables(cursor)
        conn.commit()
        print("✅ Kết nối thành công database postgresql")
    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi kết nối Database: {e}")
        raise e
    finally:
        cursor.close()
        conn.close()