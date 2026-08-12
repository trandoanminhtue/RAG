from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain_unstructured import UnstructuredLoader
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

# 1. Load documents
loader = DirectoryLoader(
    path=".././paper",
    glob="**/*.pdf",
    loader_cls=PyPDFLoader,
    show_progress=True,
    use_multithreading=True,
)
docs = loader.load()

# 2. chunk
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
splits = text_splitter.split_documents(docs)

# 3. Embedding model (Ollama local)
# Đổi tên model theo model embedding bạn đã `ollama pull`
# vd: "nomic-embed-text", "mxbai-embed-large", "bge-m3"
EMBEDDING_MODEL = "bge-m3"
embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)

# 4. Vector store FAISS in-memory
vectorstore = FAISS.from_documents(
    documents=splits,
    embedding=embeddings,
    distance_strategy=DistanceStrategy.COSINE,
)

retriever = vectorstore.as_retriever(
    search_type="similarity_score_threshold",
    search_kwargs={"k": 5, "score_threshold": 0.2},
)

# 5. Prompt
template = """You are a secretary. Use ONLY the context below to answer the question.
If the answer is not contained in the context, say you don't know.

Context:
{context}

Question: {question}

Answer:"""
prompt = ChatPromptTemplate.from_template(template)


def format_docs(docs: list[Document]) -> str:
    return "\n\n".join(d.page_content for d in docs)


# 6. LLM (Ollama local)
# Đổi tên model theo model bạn đã `ollama pull`
# vd: "llama3.1", "qwen2.5", "mistral", "gemma2"
LLM_MODEL = "qwen2.5:7b"
llm = ChatOllama(model=LLM_MODEL, temperature=0)

# 7. RAG chain
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

# 8. Run
if __name__ == "__main__":
    question = input("Question: ")
    answer = rag_chain.invoke(question)
    print(answer)