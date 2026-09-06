"""
vectorstore/ingest.py
Loads policy markdown files -> chunks -> embeds with local sentence-transformers -> persists to ChromaDB.
Run: python vectorstore/ingest.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

_USE_FAKE = os.environ.get("USE_FAKE_EMBEDDINGS", "false").lower() == "true"

if _USE_FAKE:
    from langchain_core.embeddings import FakeEmbeddings as _FakeEmbeddings
else:
    from langchain_huggingface import HuggingFaceEmbeddings

POLICIES_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "policies")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_store")
COLLECTION = "policy_docs"

HEADERS_TO_SPLIT = [
    ("#", "section"),
    ("##", "subsection"),
    ("###", "subsubsection"),
]


def build_embeddings():
    if _USE_FAKE:
        print("  [DEV MODE] Using FakeEmbeddings")
        return _FakeEmbeddings(size=1536)

    model_name = os.environ.get("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    print(f"  [LOCAL EMBEDDINGS] Using HuggingFace model: {model_name}")
    try:
        return HuggingFaceEmbeddings(model_name=model_name)
    except Exception as exc:
        print(f"  [WARN] HuggingFace embedding model could not load ({exc}). Falling back to FakeEmbeddings.")
        return _FakeEmbeddings(size=1536)

def load_and_chunk_policies():
    loader = DirectoryLoader(
        POLICIES_DIR,
        glob="*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=True,
    )
    raw_docs = loader.load()
    print(f"  Loaded {len(raw_docs)} policy files")

    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT,
        strip_headers=False,
    )
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
    )

    all_chunks = []
    for doc in raw_docs:
        source = os.path.basename(doc.metadata.get("source", "unknown"))
        md_chunks = md_splitter.split_text(doc.page_content)
        for chunk in md_chunks:
            chunk.metadata["source"] = source
        final_chunks = char_splitter.split_documents(md_chunks)
        all_chunks.extend(final_chunks)

    print(f"  Produced {len(all_chunks)} chunks")
    return all_chunks

def ingest():
    print("\n[Phase 2] Ingesting policy documents into ChromaDB...")

    chunks = load_and_chunk_policies()
    embeddings = build_embeddings()

    # Wipe and recreate collection for clean re-runs
    if os.path.exists(CHROMA_DIR):
        import shutil
        shutil.rmtree(CHROMA_DIR)
        print("  Cleared existing chroma_store")

    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=COLLECTION,
        persist_directory=CHROMA_DIR,
    )

    count = vectorstore._collection.count()
    print(f"  Stored {count} vectors in ChromaDB at: {os.path.abspath(CHROMA_DIR)}")
    return vectorstore


def reset_vectorstore():
    if os.path.exists(CHROMA_DIR):
        import shutil
        shutil.rmtree(CHROMA_DIR)
        print("  Cleared stale chroma_store")
    return ingest()


def _collection_is_stale(collection, embeddings) -> bool:
    try:
        sample = embeddings.embed_query("dimension-check")
        sample_dim = len(sample)
        first = collection.get(limit=1, include=["embeddings"])
        if not first.get("embeddings"):
            return False
        return len(first["embeddings"][0]) != sample_dim
    except Exception:
        return False


def load_vectorstore():
    """Load existing ChromaDB store — used by agents at runtime."""
    if os.path.exists(CHROMA_DIR):
        print("  [INFO] Rebuilding Chroma store to match current embedding model")
        return reset_vectorstore()
    return ingest()

if __name__ == "__main__":
    ingest()
    print("[DONE] Vector store ready.\n")
