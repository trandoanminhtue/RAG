import os
from dotenv import load_dotenv
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, FastAPI

# Document Loaders & Splitters
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.load.load import load
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Embeddings & LLM (Ollama)
from langchain_ollama import OllamaEmbeddings, ChatOllama

# Vector Store (Qdrant thay cho FAISS)
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models

# DB
from minio import Minio
import tempfile
import psycopg2
from database.model import create_tables
import pika
from io import BytesIO

# Chain & Prompts
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnablePassthrough, RunnableLambda
from langchain_core.documents import Document

load_dotenv()
# Config

#QDRANT
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = str(os.getenv("COLLECTION_NAME", "pdf_documents"))

#POSTGRESQL
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

#MINIO
MINIO_HOST = os.getenv("MINIO_HOST", "localhost")
MINIO_PORT = int(os.getenv("MINIO_PORT", 9000))
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
BUCKET_NAME = str(os.getenv("BUCKET_NAME", "documents"))

#RABBITMQ
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASSWORD", "guest")

router = APIRouter()
app = FastAPI()
# Khởi tạo

## Qdrant
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
def init_qdrant():
    if not qdrant_client.collection_exists(COLLECTION_NAME):
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=1024,
                distance=models.Distance.COSINE
            )
    )
    print(f"✅ kết nối thành công qdrant; collection: '{COLLECTION_NAME}'")

init_qdrant()
## MinIO
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

init_minio_bucket()

## RabbitMQ
credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
parameters = pika.ConnectionParameters(
    host=RABBITMQ_HOST,
    port=RABBITMQ_PORT,
    credentials=credentials
)

QUEUE_NAME = "task_queue"

def init_rabbit():
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    print(f"✅ Kết nối thành công rabbitMQ; Queue: '{QUEUE_NAME}'")
    connection.close()
init_rabbit()

## POSTGRESQL
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

init_db()

#  luồng admin
## biến
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)

vectorstore = QdrantVectorStore(
    client=qdrant_client,
    collection_name=COLLECTION_NAME,
    embedding=embeddings
)

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=200,
    add_start_index=True,
    strip_whitespace=True,
)

## hàm
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
        f"đã được tạo với status=PENDING"
    )

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

def LCE(file_path: str, document_id: str):
    loader = PyPDFLoader(file_path)
    docs = loader.load()
    splits = text_splitter.split_documents(docs)

    #chunk
    for split in splits:
        split.metadata["document_id"] = document_id

    vectorstore.add_documents(splits)

    total_chunks = len(splits)

    conn = get_db()
    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE documents
            SET
                status = 'COMPLETED',
                total_chunks = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
            """,
            (
                total_chunks,
                document_id,
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
        f"✅ Document {document_id} embedding thành công. "
        f"{total_chunks} chunks -> Qdrant"
    )

def done_admin(document_id: str):
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf",
        ) as temp_file:

            temp_file_path = temp_file.name


        minio_client.fget_object(
            bucket_name=BUCKET_NAME,
            object_name=document_id,
            file_path=temp_file_path,
        )

        LCE(file_path=temp_file_path, document_id=document_id)

    except Exception as e:

        conn = get_db()

        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE documents
                SET
                    status = 'FAILED',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
                """,
                (document_id,),
            )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            cursor.close()
            conn.close()

        print(
            f"❌ Xử lý document {document_id} thất bại: {e}"
        )

        raise

    finally:
        if (
            temp_file_path
            and os.path.exists(temp_file_path)
        ):
            os.remove(temp_file_path)

###===============================================================================================================
# luồng user
retriever = vectorstore.as_retriever(
    search_type="similarity_score_threshold",
    search_kwargs={"k": 5, "score_threshold": 0.2}
)

template = """You are a secretary. Use ONLY the context below to answer the question.
If the answer is not contained in the context, say you don't know.

Context:
{context}

Question: {question}

Answer:"""

prompt = ChatPromptTemplate.from_template(template)

LLM_MODEL = "qwen2.5:7b"
llm = ChatOllama(model=LLM_MODEL, temperature=0)

def format_docs(docs: list[Document]) -> str:
    return "\n\n".join(d.page_content for d in docs)

def handle_question(session_id: str, question: str) -> dict:
    Question = input("Nhập câu hỏi: ")

def save_ans(data: dict) -> dict:
    question = data["question"]
    answer = data["answer"]
    docs = data["context"]
    
    conn = get_db()
    cursor = conn.cursor()
    ai_message_id = cursor.fetchone()[0]

    for doc in docs:
        doc_id = doc.metadata.get("document_id")

        if doc_id:
            cursor.execute("""
                INSERT INTO message_sources (
                    message_id, 
                    document_id, 
                    page_number, 
                    content_preview
                )
                VALUES (%s, %s, %s, %s);
            """, (
                    ai_message_id,
                    doc_id,
                    doc.metadata.get("page", 1),
                    doc.page_content[:200]
                ))
            
        conn.commit()
        cursor.close()
        conn.close()

    return data

rag_chain_answer = (
    RunnablePassthrough.assign(context=(lambda x: format_docs(x["context"])))
    | prompt
    | llm
    | StrOutputParser()
)

rag_chain = (
    RunnableParallel({
        "context": (lambda x: x["question"]) | retriever,
        "question": lambda x: x["question"],
        "session_id": lambda x: x["session_id"]
    })
    .assign(answer=rag_chain_answer)
    | RunnableLambda(save_ans)
    | (lambda x: x["answer"])
)

app.include_router(router)