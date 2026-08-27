from fastapi import FastAPI
from app.database.connection import init_db
from app.clients.qdrant_client import init_qdrant
from app.clients.minio_client import init_minio_bucket
from app.clients.rabbitmq_client import init_rabbit
from app.routers import admin, user

app = FastAPI(title="RAG")

# Initialize Third-party Connections
init_db()
init_qdrant()
init_minio_bucket()
init_rabbit()

# Include Routers
app.include_router(admin.router, prefix="/upload", tags=["Admin"])
app.include_router(user.router, prefix="/new_chat", tags=["User"])
app.include_router(user.router, prefix="/ask", tags=["User"])