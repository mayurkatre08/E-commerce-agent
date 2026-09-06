"""
test_phase5.py -- Validates Phase 5: full LangGraph multi-agent workflow.
Run: python tests/test_phase5.py
"""

import os
import sys
import asyncio
import subprocess
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp_client.client import get_mcp_tools
from graph.workflow import build_graph, get_initial_state

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


async def run_graph(graph, message, customer_id=None, order_id=None):
    state  = get_initial_state(message, customer_id=customer_id, order_id=order_id)
    result = await graph.ainvoke(state)
    reply  = result["messages"][-1].content
    return result, reply


async def run_tests():
    print("\n[Phase 5] Building LangGraph workflow via MCP client...")

    async with get_mcp_tools() as tools:
        graph = build_graph(tools)
        check("graph compiled", graph is not None)
        nodes = list(graph.get_graph().nodes.keys())
        print(f"  Nodes: {nodes}")

        # -- Test 1: Policy -----------------------------------------------
        print("\n[Test 1: Policy Query]")
        result, reply = await run_graph(graph, "What is your return policy?")
        check("intent=policy",   result["intent"] == "policy",  f"got '{result['intent']}'")
        check("reply non-empty", len(reply) > 10)
        check("resolved=True",   result["resolved"] is True)
        check("escalated=False", result["escalated"] is False)
        print(f"  Reply: {reply[:100]}")

        # -- Test 2: Order lookup -----------------------------------------
        print("\n[Test 2: Order Lookup]")
        result, reply = await run_graph(
            graph, "What is the status of my order ORD9002?",
            customer_id="C002", order_id="ORD9002",
        )
        check("intent=order_lookup", result["intent"] == "order_lookup", f"got '{result['intent']}'")
        check("reply has ORD9002",   "ORD9002" in reply)
        check("reply has status",    any(s in reply.upper() for s in ["SHIPPED", "STATUS", "ORDER"]))
        check("resolved=True",       result["resolved"] is True)
        print(f"  Reply: {reply[:120]}")

        # -- Test 3: Cancel order -----------------------------------------
        print("\n[Test 3: Cancel Order]")
        result, reply = await run_graph(
            graph, "Please cancel my order ORD9001",
            customer_id="C001", order_id="ORD9001",
        )
        check("intent=cancel",          result["intent"] == "cancel", f"got '{result['intent']}'")
        check("reply mentions cancel",  any(w in reply.lower() for w in ["cancel", "cancelled", "refund"]))
        check("resolved=True",          result["resolved"] is True)
        print(f"  Reply: {reply[:120]}")

        # -- Test 4: Change size ------------------------------------------
        print("\n[Test 4: Change Size]")
        # Re-seed so ORD9004 is back to processing
        subprocess.run([sys.executable, "data/seed_db.py"], capture_output=True, cwd=os.path.join(os.path.dirname(__file__), ".."))

        result, reply = await run_graph(
            graph, "I want to change the size of order ORD9004 to XL",
            customer_id="C004", order_id="ORD9004",
        )
        check("intent=change_size",    result["intent"] == "change_size", f"got '{result['intent']}'")
        check("reply mentions size",   any(w in reply.lower() for w in ["size", "xl", "change", "updated"]))
        check("resolved=True",         result["resolved"] is True)
        print(f"  Reply: {reply[:120]}")

        # -- Test 5: Escalation -------------------------------------------
        print("\n[Test 5: Escalation]")
        result, reply = await run_graph(
            graph, "I want to speak to a human agent, this is unacceptable!",
            customer_id="C005",
        )
        check("intent=escalate",       result["intent"] == "escalate", f"got '{result['intent']}'")
        check("reply has ticket/agent", any(w in reply.lower() for w in ["ticket", "tkt", "agent", "escalat"]))
        check("escalated=True",        result["escalated"] is True)
        check("resolved=True",         result["resolved"] is True)
        print(f"  Reply: {reply[:120]}")

        # -- Test 6: Missing order_id guard --------------------------------
        print("\n[Test 6: Missing order_id guard]")
        result, reply = await run_graph(
            graph, "Can you check my order status?",
            customer_id="C001",
        )
        check("asks for order ID", any(w in reply.lower() for w in ["order id", "order number", "provide", "ord"]))
        print(f"  Reply: {reply[:120]}")

        # -- Graph structure ----------------------------------------------
        print("\n[Graph Structure]")
        graph_def     = graph.get_graph()
        expected      = {"supervisor", "rag_agent", "order_agent", "action_agent", "escalation_agent"}
        actual        = set(graph_def.nodes.keys()) - {"__start__", "__end__"}
        check("all 5 nodes present", expected == actual, f"missing: {expected - actual}")

    # -- Summary ----------------------------------------------------------
    print("\n" + "-" * 50)
    if failures:
        print(f"[FAILED] {len(failures)} check(s) failed: {failures}")
        sys.exit(1)
    else:
        print("[PASSED] All Phase 5 checks passed -- ready for Phase 6!")
    print()


if __name__ == "__main__":
    asyncio.run(run_tests())
