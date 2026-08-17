import os
from dotenv import load_dotenv

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
from backend.database.model import create_tables
import pika

# Chain & Prompts
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.documents import Document

load_dotenv()

# Config

#QDRANT
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "pdf_documents"

#POSTGRESQL
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

#MINIO
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")

#RABBITMQ
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASSWORD", "guest")

# Khởi tạo

# Qdrant
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

if not qdrant_client.collection_exists(COLLECTION_NAME):
    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=1024,
            distance=models.Distance.COSINE
        )
    )
    print(f"đã khai báo xong collection '{COLLECTION_NAME} của qdrant")

# MinIO
minio_client = Minio(
    endpoint=MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

if not minio_client.bucket_exists("documents"):
    minio_client.make_bucket("documents")
    print("Đã khai báo xong bucket minIO: documents")

# RabbitMQ
credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
parameters = pika.ConnectionParameters(
    host=RABBITMQ_HOST,
    port=RABBITMQ_PORT,
    credentials=credentials
)

connection = pika.BlockingConnection(parameters)
channel = connection.channel()

QUEUE_NAME = "task_queue"

print(f"✅ Đã khai báo xong Queue: '{QUEUE_NAME}'")
connection.close()

# POSTGRESQL
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
        print("✅ Khởi tạo Database thành công")
    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi khởi tạo Database: {e}")
        raise e
    finally:
        cursor.close()
        conn.close()

# luồng admin
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)

vectorstore = QdrantVectorStore(
    client=qdrant_client,
    collection_name=COLLECTION_NAME,
    embedding=embeddings
)

def ULminIO(file_path: str, document_id: str):
    minio_client.fput_object(
        bucket_name="documents",
        object_name=document_id,
        file_path=file_path
    )
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO documents (
            id, 
            user_id,
            file_name, 
            file_size_bytes, 
            minio_bucket, 
            minio_object_name, 
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')
        ON CONFLICT (id) DO UPDATE 
        SET status = 'PENDING',
            updated_at = CURRENT_TIMESTAMP;
    """)
    conn.commit()
    conn.close()
    print("lưu thành công file "f"{document_id} vào MinIO")

MARKDOWN_SEPARATORS = [
    "\n#{1,6} ",
    "```\n",
    "\n\\*\\*\\*+\n",
    "\n---+\n",
    "\n___+\n",
    "\n\n",
    "\n",
    " ",
    "",
]

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=200,
    add_start_index=True,
    strip_whitespace=True,
    separators=MARKDOWN_SEPARATORS,
)

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
    cursor = conn.cursor()
    
    try:
        query = """
            UPDATE documents
            SET status = 'COMPLETED',
                total_chunks = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """
        cursor.execute(query, (total_chunks, document_id))
        conn.commit()
        print(f"Lưu thành công {total_chunks} chunks của file {document_id} vào Qdrant")
    except Exception as e:
        conn.rollback()
        print(f"❌Lỗi cập nhật trạng thái: {e}")
        raise e
    finally:
        cursor.close()
        conn.close()

def TempMinIO(document_id: str):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file_path = temp_file.name
    try:
        minio_client.fget_object("documents", document_id, temp_file_path)
        
        LCE(file_path=temp_file_path, document_id=document_id)
        
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

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

def format_docs(docs: list[Document]) -> str:
    return "\n\n".join(d.page_content for d in docs)

LLM_MODEL = "qwen2.5:7b"
llm = ChatOllama(model=LLM_MODEL, temperature=0)

# RAG chain
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

if __name__ == "__main__":
    LCE("path/to/your/file.pdf", "document_1")
    question = input("Question: ")
    answer = rag_chain.invoke(question)
    print("Answer:", answer)