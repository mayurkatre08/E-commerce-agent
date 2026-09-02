"""
test_phase6.py -- Validates Phase 6: observability, metrics, LangSmith config.
Run: python tests/test_phase6.py
"""

import os
import sys
import asyncio
import subprocess
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from observability.metrics import MetricsCollector
from observability.tracer import is_tracing_enabled, get_run_config, trace_summary
from observability.instrumented_workflow import instrument_tools, run_with_observability
from mcp_client.client import get_mcp_tools
from graph.workflow import build_graph

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


# ── Unit tests: MetricsCollector ──────────────────────────────────────────────
print("\n[MetricsCollector Unit Tests]")

mc = MetricsCollector()

# Record some fake tool calls
with mc.time_tool("policy_search"):
    import time; time.sleep(0.01)

with mc.time_tool("policy_search"):
    import time; time.sleep(0.02)

with mc.time_tool("get_order"):
    import time; time.sleep(0.005)

# Simulate a failure
try:
    with mc.time_tool("cancel_order") as t:
        t.success = False
        raise ValueError("simulated failure")
except ValueError:
    pass

mc.record_run(escalated=False)
mc.record_run(escalated=True)
mc.record_run(escalated=True)
mc.record_rag_scores([2800.0, 2900.0, 3000.0])

check("policy_search has 2 calls",
      mc._tools["policy_search"].success == 2)
check("cancel_order has 1 failure",
      mc._tools["cancel_order"].failure == 1)
check("total runs = 3",
      mc._runs == 3)
check("escalated runs = 2",
      mc._escalated == 2)
check("escalation_rate = 0.6667",
      abs(mc.escalation_rate() - 0.6667) < 0.001,
      f"got {mc.escalation_rate()}")
check("policy_search success_rate = 1.0",
      mc.tool_success_rate("policy_search") == 1.0)
check("cancel_order success_rate = 0.0",
      mc.tool_success_rate("cancel_order") == 0.0)
check("p95 latency is float",
      isinstance(mc.tool_p95_latency_ms("policy_search"), float))
check("avg_rag_groundedness is float",
      isinstance(mc.avg_rag_groundedness(), float))
check("avg_rag_groundedness in [0,1]",
      0.0 <= mc.avg_rag_groundedness() <= 1.0,
      f"got {mc.avg_rag_groundedness()}")

report = mc.report()
check("report has 'tools' key",         "tools" in report)
check("report has 'escalation_rate'",   "escalation_rate" in report)
check("report has 'total_runs'",        "total_runs" in report)
check("report tools has policy_search", "policy_search" in report["tools"])
check("report tools has p95_latency_ms",
      report["tools"]["policy_search"]["p95_latency_ms"] is not None)

# ── LangSmith tracer ──────────────────────────────────────────────────────────
print("\n[LangSmith Tracer]")

trace_summary()
check("is_tracing_enabled returns bool",  isinstance(is_tracing_enabled(), bool))
check(
    "tracing state matches env config",
    is_tracing_enabled() == bool(os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")),
)

config = get_run_config(session_id="test-001", customer_id="C001", intent="policy")
check("config has tags",                  len(config.get("tags", [])) > 0)
check("config has ecommerce-agent tag",   "ecommerce-agent" in config.get("tags", []))
check("config has intent tag",            "intent:policy" in config.get("tags", []))
check("config has metadata",              bool(config.get("metadata")))
check("metadata has session_id",          config["metadata"]["session_id"] == "test-001")
check("metadata has customer_id",         config["metadata"]["customer_id"] == "C001")

# ── Integration: instrumented workflow ────────────────────────────────────────
print("\n[Instrumented Workflow Integration]")

async def run_integration():
    # Re-seed DB
    subprocess.run(
        [sys.executable, "data/seed_db.py"],
        capture_output=True,
        cwd=os.path.join(os.path.dirname(__file__), "..")
    )

    async with get_mcp_tools() as raw_tools:
        # Instrument tools
        tools = instrument_tools(raw_tools)
        check("tools instrumented",         len(tools) == 5)
        check("tools still BaseTool",       all(hasattr(t, "ainvoke") for t in tools))

        graph = build_graph(tools)

        # Run 1: policy query
        r1 = await run_with_observability(
            graph, "What is your return policy?",
            session_id="sess-001"
        )
        check("run1 has _run_ms",           "_run_ms" in r1)
        check("run1 _run_ms > 0",           r1["_run_ms"] > 0)
        check("run1 has _session_id",       r1["_session_id"] == "sess-001")
        check("run1 intent=policy",         r1["intent"] == "policy")
        check("run1 escalated=False",       r1["escalated"] is False)

        # Run 2: order lookup
        r2 = await run_with_observability(
            graph, "What is the status of my order ORD9002?",
            customer_id="C002", order_id="ORD9002", session_id="sess-002"
        )
        check("run2 intent=order_lookup",   r2["intent"] == "order_lookup")

        # Run 3: escalation
        r3 = await run_with_observability(
            graph, "I want to speak to a human agent!",
            customer_id="C005", session_id="sess-003"
        )
        check("run3 intent=escalate",       r3["intent"] == "escalate")
        check("run3 escalated=True",        r3["escalated"] is True)

        # Validate metrics were collected across all 3 runs
        from observability.metrics import metrics as global_metrics
        report = global_metrics.report()

        check("metrics recorded runs >= 3",
              report["total_runs"] >= 3,
              f"got {report['total_runs']}")
        check("policy_search was called",
              "policy_search" in report["tools"],
              f"tools seen: {list(report['tools'].keys())}")
        check("policy_search success_rate = 1.0",
              report["tools"]["policy_search"]["success_rate"] == 1.0)
        check("get_order was called",
              "get_order" in report["tools"])
        check("escalate_to_human was called",
              "escalate_to_human" in report["tools"])
        check("escalation_rate > 0",
              report["escalation_rate"] > 0,
              f"got {report['escalation_rate']}")
        check("rag_groundedness recorded",
              report["avg_rag_groundedness"] is not None)

        # Print the full report
        global_metrics.print_report()

asyncio.run(run_integration())

# ── Summary ───────────────────────────────────────────────────────────────────
print("-" * 50)
if failures:
    print(f"[FAILED] {len(failures)} check(s) failed: {failures}")
    sys.exit(1)
else:
    print("[PASSED] All Phase 6 checks passed -- ready for Phase 7!")
print()
