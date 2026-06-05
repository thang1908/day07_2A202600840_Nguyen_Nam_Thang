from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from main import SAMPLE_FILES, build_metadata_for_path
from src import (
    EMBEDDING_PROVIDER_ENV,
    LOCAL_EMBEDDING_MODEL,
    OPENAI_EMBEDDING_MODEL,
    Document,
    EmbeddingStore,
    FixedSizeChunker,
    LocalEmbedder,
    MarkdownStructureChunker,
    OpenAIEmbedder,
    RecursiveChunker,
    SentenceChunker,
    _mock_embed,
)

load_dotenv(override=False)

app = FastAPI(title="Viettel FAQ RAG Lab")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class IndexRequest(BaseModel):
    chunk_method: str = Field(default="markdown")
    chunk_size: int = Field(default=1200, ge=200, le=6000)
    overlap: int = Field(default=100, ge=0, le=1000)
    max_sentences: int = Field(default=3, ge=1, le=20)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    domain: str | None = None
    doc_id: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    domain: str | None = None
    doc_id: str | None = None


@dataclass
class AppState:
    store: EmbeddingStore | None = None
    documents: list[Document] = field(default_factory=list)
    chunk_method: str = ""
    chunk_size: int = 0
    embedding_backend: str = ""
    use_chroma: bool = False
    total_files: int = 0
    total_chunks: int = 0
    domains: list[str] = field(default_factory=list)
    doc_ids: list[str] = field(default_factory=list)


state = AppState()


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    return status_payload()


@app.post("/api/index")
def build_index(request: IndexRequest) -> dict[str, Any]:
    if request.chunk_method not in {"markdown", "recursive", "fixed", "sentence"}:
        raise HTTPException(status_code=400, detail="Unsupported chunk method")

    embedder = create_embedder()
    documents = load_chunk_documents(request)
    if not documents:
        raise HTTPException(status_code=400, detail="No documents were loaded")

    store = EmbeddingStore(collection_name="viettel_faq_app", embedding_fn=embedder)
    try:
        store.add_documents(documents)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}") from exc

    state.store = store
    state.documents = documents
    state.chunk_method = request.chunk_method
    state.chunk_size = request.chunk_size
    state.embedding_backend = getattr(embedder, "_backend_name", embedder.__class__.__name__)
    state.use_chroma = store._use_chroma
    state.total_files = len(SAMPLE_FILES)
    state.total_chunks = store.get_collection_size()
    state.domains = sorted({doc.metadata.get("domain", "") for doc in documents if doc.metadata.get("domain")})
    state.doc_ids = sorted({doc.metadata.get("doc_id", "") for doc in documents if doc.metadata.get("doc_id")})

    return status_payload()


@app.post("/api/query")
def query_index(request: QueryRequest) -> dict[str, Any]:
    if state.store is None:
        raise HTTPException(status_code=400, detail="Build the index before querying")

    metadata_filter = None
    if request.doc_id:
        metadata_filter = {"doc_id": request.doc_id}
    elif request.domain:
        metadata_filter = {"domain": request.domain}

    results = state.store.search_with_filter(
        request.question,
        top_k=request.top_k,
        metadata_filter=metadata_filter,
    )

    return {
        "question": request.question,
        "metadata_filter": metadata_filter,
        "results": [
            {
                "rank": index,
                "score": result["score"],
                "content": result["content"],
                "metadata": result["metadata"],
            }
            for index, result in enumerate(results, start=1)
        ],
    }


@app.post("/api/chat")
def chat_with_knowledge_base(request: ChatRequest) -> dict[str, Any]:
    if state.store is None:
        raise HTTPException(status_code=400, detail="Build the index before chatting")

    metadata_filter = build_metadata_filter(request.domain, request.doc_id)
    results = state.store.search_with_filter(
        request.message,
        top_k=request.top_k,
        metadata_filter=metadata_filter,
    )
    answer = answer_with_llm(request.message, results)

    return {
        "answer": answer,
        "metadata_filter": metadata_filter,
        "sources": [
            {
                "rank": index,
                "score": result["score"],
                "source": result["metadata"].get("source"),
                "doc_id": result["metadata"].get("doc_id"),
                "section_title": result["metadata"].get("section_title"),
            }
            for index, result in enumerate(results, start=1)
        ],
    }


def create_embedder():
    provider = os.getenv(EMBEDDING_PROVIDER_ENV, "mock").strip().lower()
    if provider == "local":
        try:
            return LocalEmbedder(model_name=os.getenv("LOCAL_EMBEDDING_MODEL", LOCAL_EMBEDDING_MODEL))
        except Exception:
            return _mock_embed
    if provider == "openai":
        try:
            return OpenAIEmbedder(model_name=os.getenv("OPENAI_EMBEDDING_MODEL", OPENAI_EMBEDDING_MODEL))
        except Exception:
            return _mock_embed
    return _mock_embed


def build_metadata_filter(domain: str | None, doc_id: str | None) -> dict[str, str] | None:
    if doc_id:
        return {"doc_id": doc_id}
    if domain:
        return {"domain": domain}
    return None


def answer_with_llm(question: str, results: list[dict[str, Any]]) -> str:
    prompt = build_answer_prompt(question, results)

    try:
        from openai import OpenAI

        client = OpenAI()
        model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Vietnamese customer support assistant. "
                        "Answer only from the provided context. "
                        "If the context is not enough, say you do not have enough information."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
    except Exception:
        preview = "\n\n".join(result["content"][:450] for result in results[:2])
        if not preview:
            return "Chưa có context phù hợp để trả lời câu hỏi này."
        return (
            "Không gọi được LLM, nhưng đây là context liên quan nhất để bạn kiểm tra:\n\n"
            f"{preview}"
        )


def build_answer_prompt(question: str, results: list[dict[str, Any]]) -> str:
    context_blocks = []
    for index, result in enumerate(results, start=1):
        metadata = result.get("metadata", {})
        source = metadata.get("source") or metadata.get("doc_id") or result.get("id", "unknown")
        section = metadata.get("section_title") or metadata.get("heading_path") or ""
        context_blocks.append(
            f"[{index}] Source: {source}\nSection: {section}\nScore: {result['score']:.4f}\n{result['content']}"
        )

    context = "\n\n".join(context_blocks) if context_blocks else "No relevant context was found."
    return (
        "Hãy trả lời câu hỏi bằng tiếng Việt, ngắn gọn và dựa trên context dưới đây.\n"
        "Nếu context không đủ, hãy nói rõ là chưa đủ thông tin.\n\n"
        f"Context:\n{context}\n\n"
        f"Câu hỏi: {question}\n"
        "Trả lời:"
    )


def load_chunk_documents(request: IndexRequest) -> list[Document]:
    documents: list[Document] = []

    for raw_path in SAMPLE_FILES:
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue

        content = path.read_text(encoding="utf-8")
        base_metadata = build_metadata_for_path(path)
        chunk_records = chunk_content(content, base_metadata, request)

        for record in chunk_records:
            metadata = record["metadata"]
            documents.append(
                Document(
                    id=metadata["chunk_id"],
                    content=record["content"],
                    metadata=metadata,
                )
            )

    return documents


def chunk_content(
    content: str,
    base_metadata: dict[str, Any],
    request: IndexRequest,
) -> list[dict[str, Any]]:
    if request.chunk_method == "markdown":
        chunker = MarkdownStructureChunker(chunk_size=request.chunk_size)
        return chunker.chunk_with_metadata(content, base_metadata)

    if request.chunk_method == "fixed":
        chunker = FixedSizeChunker(chunk_size=request.chunk_size, overlap=min(request.overlap, request.chunk_size - 1))
        chunks = chunker.chunk(content)
    elif request.chunk_method == "sentence":
        chunker = SentenceChunker(max_sentences_per_chunk=request.max_sentences)
        chunks = chunker.chunk(content)
    else:
        chunker = RecursiveChunker(chunk_size=request.chunk_size)
        chunks = chunker.chunk(content)

    doc_id = base_metadata.get("doc_id", "document")
    records = []
    for index, chunk in enumerate(chunks):
        metadata = {
            **base_metadata,
            "chunk_index": index,
            "chunk_id": f"{doc_id}_chunk_{index}",
            "heading_path": "",
            "section_title": "",
        }
        records.append({"content": chunk, "metadata": metadata})
    return records


def status_payload() -> dict[str, Any]:
    return {
        "indexed": state.store is not None,
        "embedding_backend": state.embedding_backend or "not initialized",
        "vector_db": "ChromaDB" if state.use_chroma else "in-memory fallback",
        "chunk_method": state.chunk_method or "not indexed",
        "chunk_size": state.chunk_size,
        "total_files": state.total_files,
        "total_chunks": state.total_chunks,
        "domains": state.domains,
        "doc_ids": state.doc_ids,
    }
