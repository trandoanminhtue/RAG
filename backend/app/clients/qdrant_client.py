from qdrant_client import QdrantClient
from qdrant_client.http import models
from config import QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME, VECTOR_SIZE

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def init_qdrant():
    if not qdrant_client.collection_exists(COLLECTION_NAME):
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_SIZE,
                distance=models.Distance.COSINE
            )
    )
    print(f"✅ kết nối thành công qdrant; collection: '{COLLECTION_NAME}'")