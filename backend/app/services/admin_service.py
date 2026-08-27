import os
import uuid
import tempfile
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore

from config import OLLAMA_BASE_URL, EMBEDDING_MODEL, COLLECTION_NAME, BUCKET_NAME
from app.clients.qdrant_client import qdrant_client
from app.database.connection import get_db
from app.clients.minio_client import minio_client

embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)

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