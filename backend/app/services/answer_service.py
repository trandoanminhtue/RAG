from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import ChatOllama

from app.services.admin_service import vectorstore
from config import OLLAMA_BASE_URL, LLM_MODEL


retriever = vectorstore.as_retriever(
    search_type="similarity_score_threshold",
    search_kwargs={"k": 5,
                   "score_threshold": 0.2
    },
)

def format_docs(docs: list[Document]) -> str:
    return "\n\n".join(d.page_content for d in docs)

template = """
Bạn là một trợ lý AI chuyên nghiệp. Hãy trả lời câu hỏi của người dùng DỰA TRÊN ngữ cảnh được cung cấp dưới đây.

YÊU CẦU BẮT BUỘC:
1. Luôn luôn trả lời bằng **Tiếng Việt**.
2. Nếu ngữ cảnh chứa ngôn ngữ khác (Tiếng Anh, Tiếng Trung...), hãy tự dịch và tổng hợp lại bằng Tiếng Việt.
3. Nếu không tìm thấy thông tin trong ngữ cảnh, hãy trả lời: "Tôi không tìm thấy thông tin này trong tài liệu."

Ngữ cảnh (Context):
{context}

Câu hỏi:
{question}

Trả lời:
"""

prompt = ChatPromptTemplate.from_template(template)

llm = ChatOllama(model=LLM_MODEL, temperature=0, base_url=OLLAMA_BASE_URL)



chain = (
    prompt | llm | StrOutputParser()
)