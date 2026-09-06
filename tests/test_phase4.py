"""
test_phase4.py -- Validates Phase 4: MCP client connects to server and
                  exposes all 5 tools as LangChain BaseTools.
Run: python tests/test_phase4.py
"""

import os
import sys
import asyncio
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp_client.client import get_mcp_tools, get_tool_names

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


async def run_tests():

    # -- Tool names (no subprocess needed) ------------------------------------
    print("\n[Expected Tool Names]")
    names = get_tool_names()
    check("5 tools defined", len(names) == 5, f"got {len(names)}")
    for n in names:
        check(f"  '{n}' in list", n in names)

    # -- Connect via MCP stdio and load tools ---------------------------------
    print("\n[MCP Client Connection]")
    print("  Spawning MCP server subprocess...")

    async with get_mcp_tools() as tools:
        check("tools list is non-empty",    len(tools) > 0, f"got {len(tools)}")
        check("exactly 5 tools loaded",     len(tools) == 5, f"got {len(tools)}")

        loaded_names = {t.name for t in tools}
        for expected in get_tool_names():
            check(f"tool '{expected}' loaded", expected in loaded_names)

        # -- Tool schema / metadata -------------------------------------------
        print("\n[Tool Metadata]")
        for tool in tools:
            check(f"'{tool.name}' has description", bool(tool.description))
            print(f"    {tool.name}: {tool.description[:70].strip()}...")

        # -- Tool invocations via ainvoke --------------------------------------
        print("\n[Tool Invocations via ainvoke]")

        tool_map = {t.name: t for t in tools}

        # 1. policy_search
        r = await tool_map["policy_search"].ainvoke({"query": "how do I return an item"})
        check("policy_search returns result",   bool(r))
        check("policy_search has chunks key",   "chunks" in str(r))
        print(f"    policy_search snippet: {str(r)[:80].strip()}")

        # 2. get_order -- happy path
        r = await tool_map["get_order"].ainvoke({"order_id": "ORD9001", "customer_id": "C001"})
        check("get_order ORD9001 found",        "true" in str(r).lower() or "found" in str(r).lower())
        print(f"    get_order snippet: {str(r)[:80].strip()}")

        # 3. get_order -- missing order
        r = await tool_map["get_order"].ainvoke({"order_id": "ORD0000"})
        check("get_order missing returns error", "false" in str(r).lower() or "not found" in str(r).lower())

        # 4. cancel_order -- guard: shipped
        r = await tool_map["cancel_order"].ainvoke({"order_id": "ORD9002", "customer_id": "C002"})
        check("cancel_order shipped blocked",   "false" in str(r).lower() or "cannot" in str(r).lower())
        print(f"    cancel_order guard: {str(r)[:80].strip()}")

        # 5. change_size -- guard: invalid size
        r = await tool_map["change_size"].ainvoke({
            "order_id": "ORD9001", "customer_id": "C001", "new_size": "XXXL"
        })
        check("change_size invalid blocked",    "false" in str(r).lower() or "available" in str(r).lower())
        print(f"    change_size guard: {str(r)[:80].strip()}")

        # 6. escalate_to_human
        r = await tool_map["escalate_to_human"].ainvoke({
            "customer_id": "C007",
            "reason": "Cannot resolve billing issue",
            "conversation_summary": "Customer asked about a duplicate charge.",
            "order_id": None,
        })
        check("escalate_to_human succeeds",     "tkt-" in str(r).lower() or "ticket" in str(r).lower())
        print(f"    escalate snippet: {str(r)[:80].strip()}")

    # -- Summary ---------------------------------------------------------------
    print("\n" + "-" * 50)
    if failures:
        print(f"[FAILED] {len(failures)} check(s) failed: {failures}")
        sys.exit(1)
    else:
        print("[PASSED] All Phase 4 checks passed -- ready for Phase 5!")
    print()


if __name__ == "__main__":
    asyncio.run(run_tests())
