"""
observability/tracer.py
LangSmith tracing configuration and run metadata helpers.

When LANGCHAIN_API_KEY is a real key, every graph.ainvoke() call is
automatically traced end-to-end by LangSmith (no extra code needed —
LangChain picks up the env vars).

This module adds:
  - is_tracing_enabled()  : check if real credentials are set
  - get_run_config()      : returns RunnableConfig with tags + metadata
  - trace_summary()       : print what would be traced
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def is_tracing_enabled() -> bool:
    tracing_enabled = os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    return tracing_enabled and api_key not in (None, "", "your-langsmith-api-key")


def get_run_config(
    session_id: str,
    customer_id: str = None,
    intent: str = None,
    extra_tags: list[str] = None,
) -> RunnableConfig:
    """
    Returns a RunnableConfig that attaches metadata and tags to a
    LangSmith trace run.

    Args:
        session_id:  Unique ID for this conversation turn (e.g. UUID)
        customer_id: Customer being served
        intent:      Classified intent for this turn
        extra_tags:  Any additional tags (e.g. ["prod", "v1"])
    """
    tags = ["ecommerce-agent"]
    if intent:
        tags.append(f"intent:{intent}")
    if extra_tags:
        tags.extend(extra_tags)

    metadata = {
        "session_id": session_id,
        "customer_id": customer_id or "unknown",
        "intent": intent or "unknown",
        "project": os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT", "ecommerce-agent"),
    }

    return RunnableConfig(tags=tags, metadata=metadata)


def trace_summary():
    """Print current tracing configuration."""
    enabled = is_tracing_enabled()
    project = os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT", "ecommerce-agent")
    print("\n[LangSmith Tracing]")
    print(f"  Enabled : {enabled}")
    print(f"  Project : {project}")
    if enabled:
        print(f"  Endpoint: https://smith.langchain.com/projects/{project}")
    else:
        print("  Status  : DEV MODE — set LANGCHAIN_API_KEY to enable real tracing")
    print()
