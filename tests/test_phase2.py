"""
test_phase2.py -- Validates Phase 2: ChromaDB ingestion and retrieval.
Run: python tests/test_phase2.py
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vectorstore.ingest import load_vectorstore, CHROMA_DIR, COLLECTION

failures = []

def check(label, condition, detail=""):
    if condition:
        print(f"  [PASS] {label}")
    else:
        msg = f"  [FAIL] {label}"
        if detail:
            msg += f" -- {detail}"
        print(msg)
        failures.append(label)

# -- ChromaDB store exists -----------------------------------------------------
print("\n[ChromaDB Store]")
check("chroma_store directory exists", os.path.isdir(CHROMA_DIR), f"expected at {CHROMA_DIR}")

# -- Load vectorstore ----------------------------------------------------------
print("\n[Load VectorStore]")
try:
    vs = load_vectorstore()
    count = vs._collection.count()
    check("vectorstore loads without error", True)
    check(f"collection '{COLLECTION}' has >= 30 vectors (got {count})", count >= 30, f"only {count} vectors")
except Exception as e:
    check("vectorstore loads without error", False, str(e))
    print("\n[WARNING] Run `python vectorstore/ingest.py` first.\n")
    sys.exit(1)

# -- Similarity search ---------------------------------------------------------
print("\n[Similarity Search]")

_USE_FAKE = os.environ.get("USE_FAKE_EMBEDDINGS", "false").lower() == "true"
if _USE_FAKE:
    print("  [DEV MODE] Skipping semantic source-match checks (FakeEmbeddings active)")

queries = [
    ("return policy",        "returns.md"),
    ("shipping cost",        "shipping.md"),
    ("size chart",           "sizing.md"),
    ("cancel my order",      "cancellation.md"),
    ("payment methods",      "payment.md"),
    ("exchange for size",    "exchanges.md"),
]

for query, expected_source in queries:
    results = vs.similarity_search(query, k=3)
    check(f"query '{query}' returns 3 results", len(results) == 3, f"got {len(results)}")
    if not _USE_FAKE:
        sources = [os.path.basename(r.metadata.get("source", "")) for r in results]
        check(
            f"query '{query}' top result from {expected_source}",
            expected_source in sources,
            f"got sources: {sources}"
        )

# -- Similarity search with score ----------------------------------------------
print("\n[Similarity Search with Score]")
results_with_score = vs.similarity_search_with_score("how do I return an item", k=3)
check("similarity_search_with_score returns results", len(results_with_score) > 0)
for doc, score in results_with_score:
    source = os.path.basename(doc.metadata.get("source", "unknown"))
    print(f"    score={score:.4f} | source={source} | snippet={doc.page_content[:60].strip()!r}")

# -- Retriever interface -------------------------------------------------------
print("\n[Retriever Interface]")
retriever = vs.as_retriever(search_kwargs={"k": 4})
docs = retriever.invoke("what sizes do you carry")
check("retriever.invoke returns docs", len(docs) > 0, f"got {len(docs)}")
check("retriever returns <= 4 docs", len(docs) <= 4)

# -- Metadata integrity --------------------------------------------------------
print("\n[Metadata Integrity]")
all_docs = vs.similarity_search("policy", k=10)
sources_found = {os.path.basename(d.metadata.get("source", "")) for d in all_docs}
check("metadata 'source' field present on all results", all(d.metadata.get("source") for d in all_docs))
print(f"    Sources found in top-10: {sorted(sources_found)}")

# -- Summary -------------------------------------------------------------------
print("\n" + "-" * 50)
if failures:
    print(f"[FAILED] {len(failures)} check(s) failed: {failures}")
    sys.exit(1)
else:
    print("[PASSED] All Phase 2 checks passed -- ready for Phase 3!")
print()
