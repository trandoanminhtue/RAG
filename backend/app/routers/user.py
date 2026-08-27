import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, FastAPI
from pydantic import BaseModel
from typing import Optional

from app.database.connection import get_db
from app.services.user_service import process, save



router = APIRouter()

class NewChatRequest(BaseModel):
    user_id: str
    title: Optional[str] = None

class AskRequest(BaseModel):
    session_id: str
    user_id: str
    content: str

@router.post("/new_chat")
def new_chat(payload: NewChatRequest):
    session_id = str(uuid.uuid4())
    chat_title = payload.title if payload.title else "Cuộc trò chuyện mới"

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO chat_sessions (id, user_id, title)
            VALUES (%s, %s, %s);
            """,
            (session_id, payload.user_id, chat_title)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Không thể tạo đoạn chat mới: {str(e)}")
    finally:
        cursor.close()
        conn.close()

    return {
        "session_id": session_id,
        "user_id": payload.user_id,
        "title": chat_title
    }


@router.post("/ask")
def ask(payload: AskRequest):
    print("✅ Đã nhận request, bắt đầu xử lý RAG...")
    rag_result = process(question=payload.content)
    print("✅ Đã xử lý RAG xong, chuẩn bị lưu DB...")
    answer = rag_result["answer"]
    citations = rag_result["citations"]

    try:
        save(
            session_id=payload.session_id,
            question=payload.content,
            answer=answer,
            citations=citations
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu dữ liệu hội thoại: {str(e)}")

    return {
        "session_id": payload.session_id,
        "question": payload.content,
        "answer": answer,
        "citations": citations
    }