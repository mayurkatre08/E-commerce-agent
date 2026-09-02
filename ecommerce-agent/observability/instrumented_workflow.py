"""
observability/instrumented_workflow.py
Wraps the LangGraph workflow with metrics instrumentation.

Patches each MCP tool with a timing wrapper so every tool call is
automatically recorded in MetricsCollector without touching agent code.
"""

import json
import uuid
import time
from typing import Optional

from langchain_core.tools import BaseTool
from observability.metrics import metrics
from observability.tracer import get_run_config, is_tracing_enabled


# ---------------------------------------------------------------------------
# Tool instrumentation
# ---------------------------------------------------------------------------

class _InstrumentedTool(BaseTool):
    """
    Wraps a BaseTool, recording latency + success in MetricsCollector
    for every ainvoke call. Also extracts RAG chunk scores.
    """
    _inner: BaseTool = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, inner: BaseTool):
        super().__init__(name=inner.name, description=inner.description)
        object.__setattr__(self, "_inner", inner)

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use ainvoke")

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError("Use ainvoke")

    async def ainvoke(self, input, config=None, **kwargs):
        start   = time.perf_counter()
        success = True
        result  = None
        try:
            result = await self._inner.ainvoke(input, config=config, **kwargs)
            return result
        except Exception:
            success = False
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            metrics._record(self.name, elapsed_ms, success)

            # Extract RAG scores for groundedness tracking
            if self.name == "policy_search" and result is not None:
                try:
                    if isinstance(result, list):
                        text = next((b["text"] for b in result if b.get("type") == "text"), "{}")
                        data = json.loads(text)
                    elif isinstance(result, str):
                        data = json.loads(result)
                    else:
                        data = result
                    scores = [c["score"] for c in data.get("chunks", []) if "score" in c]
                    if scores:
                        metrics.record_rag_scores(scores)
                except Exception:
                    pass


def instrument_tools(tools: list[BaseTool]) -> list[BaseTool]:
    """Wrap all MCP tools with metrics instrumentation."""
    return [_InstrumentedTool(t) for t in tools]


# ---------------------------------------------------------------------------
# Instrumented graph runner
# ---------------------------------------------------------------------------

async def run_with_observability(
    graph,
    user_message: str,
    customer_id: Optional[str] = None,
    order_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Run the LangGraph workflow with full observability:
      - Metrics timing around the full run
      - LangSmith RunnableConfig with tags + metadata
      - Escalation tracking

    Returns the final AgentState dict.
    """
    from graph.workflow import get_initial_state

    session_id = session_id or str(uuid.uuid4())[:8]
    state      = get_initial_state(user_message, customer_id=customer_id, order_id=order_id)

    # Build run config for LangSmith (works even when tracing is disabled)
    config = get_run_config(
        session_id=session_id,
        customer_id=customer_id,
        intent=None,   # not known yet — supervisor will set it
    )

    run_start = time.perf_counter()
    result    = await graph.ainvoke(state, config=config)
    run_ms    = (time.perf_counter() - run_start) * 1000

    # Record run-level metrics
    escalated = result.get("escalated", False)
    metrics.record_run(escalated=escalated)

    # Attach timing to result for caller inspection
    result["_run_ms"]     = round(run_ms, 2)
    result["_session_id"] = session_id

    return result
