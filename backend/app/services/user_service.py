import time
import json
from langchain_core.documents import Document

from app.services.answer_service import retriever, format_docs, chain
from app.database.connection import get_db

def process(question: str):
    t0 = time.time()
    docs: list[Document] = retriever.invoke(question)
    t1 = time.time()
    print(f"⏱️ Retrieval mất: {t1 - t0:.2f}s")
    context_text = format_docs(docs)

    citations = [
        {
            "id": doc.metadata.get("document_id"),
            "page": doc.metadata.get("page", None),
            "title": doc.metadata.get("title"),
            "snippet": doc.page_content[:200]
        }
        for doc in docs
    ]

    answer = chain.invoke({
        "context": context_text,
        "question": question
    })
    t2 = time.time()
    print(f"⏱️ LLM Generate mất: {t2 - t1:.2f}s")
    return {
        "answer": answer,
        "citations": citations
    }

def save(session_id: str, question: str, answer: str, citations: list) -> None:
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO chat_messages (
                session_id,
                role,
                content
            )
            VALUES (%s, 'user', %s)
            """,
            (
                session_id,
                question,
            )
        )

        cursor.execute(
            """
            INSERT INTO chat_messages (
                session_id,
                role,
                content,
                metadata
            )
            VALUES (%s, 'agent', %s, %s)
            """,
            (
                session_id,
                answer,
                json.dumps(citations)
            )
        )
        conn.commit()
        print(f"✅ đã lưu câu hỏi và câu trả lời mới của {session_id}")

    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi khi lưu vào Database: {e}")
        raise e

    finally:
        cursor.close()
        conn.close()