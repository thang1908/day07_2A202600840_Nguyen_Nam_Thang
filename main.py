from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.agent import KnowledgeBaseAgent
from src.embeddings import (
    EMBEDDING_PROVIDER_ENV,
    LOCAL_EMBEDDING_MODEL,
    OPENAI_EMBEDDING_MODEL,
    LocalEmbedder,
    OpenAIEmbedder,
    _mock_embed,
)
from src.models import Document
from src.store import EmbeddingStore

SAMPLE_FILES = [
    "data/Viettel - Business Service FAQs.md",
    "data/Viettel - Digital Application FAQs.md",
    "data/Viettel - Internet - TV FAQs.md",
    "data/Viettel - Mobile FAQs.md",
    "data/Viettel - MyViettel FAQs.md",
    "data/Viettel - Shop Viettet FAQs.md",
]

METADATA_BY_SOURCE = {
    "Viettel - Business Service FAQs.md": {
        "doc_id": "viettel_business_service_faqs",
        "domain": "business",
        "source": "Viettel - Business Service FAQs.md",
    },
    "Viettel - Digital Application FAQs.md": {
        "doc_id": "viettel_digital_application_faqs",
        "domain": "digital",
        "source": "Viettel - Digital Application FAQs.md",
    },
    "Viettel - Internet - TV FAQs.md": {
        "doc_id": "viettel_internet_tv_faqs",
        "domain": "internet",
        "source": "Viettel - Internet - TV FAQs.md",
    },
    "Viettel - Mobile FAQs.md": {
        "doc_id": "viettel_mobile_faqs",
        "domain": "mobile",
        "source": "Viettel - Mobile FAQs.md",
    },
    "Viettel - MyViettel FAQs.md": {
        "doc_id": "viettel_myviettel_faqs",
        "domain": "digital",
        "source": "Viettel - MyViettel FAQs.md",
    },
    "Viettel - Shop Viettet FAQs.md": {
        "doc_id": "viettel_shop_faqs",
        "domain": "shop",
        "source": "Viettel - Shop Viettet FAQs.md",
    },
}


def build_metadata_for_path(path: Path) -> dict:
    """Build metadata for one input file."""
    return METADATA_BY_SOURCE.get(
        path.name,
        {
            "doc_id": path.stem,
            "domain": "unknown",
            "source": path.name,
        },
    )


def load_documents_from_files(file_paths: list[str]) -> list[Document]:
    """Load documents from file paths for the manual demo."""
    allowed_extensions = {".md", ".txt"}
    documents: list[Document] = []

    for raw_path in file_paths:
        path = Path(raw_path)

        if path.suffix.lower() not in allowed_extensions:
            print(f"Skipping unsupported file type: {path} (allowed: .md, .txt)")
            continue

        if not path.exists() or not path.is_file():
            print(f"Skipping missing file: {path}")
            continue

        content = path.read_text(encoding="utf-8")
        metadata = build_metadata_for_path(path)
        documents.append(
            Document(
                id=metadata.get("doc_id", path.stem),
                content=content,
                metadata=metadata,
            )
        )

    return documents


def demo_llm(prompt: str) -> str:
    """A simple mock LLM for manual RAG testing."""
    preview = prompt[:400].replace("\n", " ")
    return f"[DEMO LLM] Generated answer from prompt preview: {preview}..."


def run_manual_demo(question: str | None = None, sample_files: list[str] | None = None) -> int:
    files = sample_files or SAMPLE_FILES
    query = question or "Summarize the key information from the loaded files."

    print("=== Manual File Test ===")
    print("Accepted file types: .md, .txt")
    print("Input file list:")
    for file_path in files:
        print(f"  - {file_path}")

    docs = load_documents_from_files(files)
    if not docs:
        print("\nNo valid input files were loaded.")
        print("Create files matching the sample paths above, then rerun:")
        print("  python3 main.py")
        return 1

    print(f"\nLoaded {len(docs)} documents")
    for doc in docs:
        print(f"  - {doc.id}: {doc.metadata['source']}")

    load_dotenv(override=False)
    provider = os.getenv(EMBEDDING_PROVIDER_ENV, "mock").strip().lower()
    if provider == "local":
        try:
            embedder = LocalEmbedder(model_name=os.getenv("LOCAL_EMBEDDING_MODEL", LOCAL_EMBEDDING_MODEL))
        except Exception:
            embedder = _mock_embed
    elif provider == "openai":
        try:
            embedder = OpenAIEmbedder(model_name=os.getenv("OPENAI_EMBEDDING_MODEL", OPENAI_EMBEDDING_MODEL))
        except Exception:
            embedder = _mock_embed
    else:
        embedder = _mock_embed

    print(f"\nEmbedding backend: {getattr(embedder, '_backend_name', embedder.__class__.__name__)}")

    store = EmbeddingStore(collection_name="manual_test_store", embedding_fn=embedder)
    store.add_documents(docs)

    print(f"\nStored {store.get_collection_size()} documents in EmbeddingStore")
    print("\n=== EmbeddingStore Search Test ===")
    print(f"Query: {query}")
    search_results = store.search(query, top_k=3)
    for index, result in enumerate(search_results, start=1):
        print(f"{index}. score={result['score']:.3f} source={result['metadata'].get('source')}")
        print(f"   content preview: {result['content'][:120].replace(chr(10), ' ')}...")

    print("\n=== KnowledgeBaseAgent Test ===")
    agent = KnowledgeBaseAgent(store=store, llm_fn=demo_llm)
    print(f"Question: {query}")
    print("Agent answer:")
    print(agent.answer(query, top_k=3))
    return 0


def main() -> int:
    question = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else None
    return run_manual_demo(question=question)


if __name__ == "__main__":
    raise SystemExit(main())
