"""
test_phase3.py -- Validates Phase 3: all 5 MCP tool functions.
Calls tool functions directly (no MCP transport needed).
Run: python tests/test_phase3.py
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import tool functions directly from the server module
from mcp_server.server import (
    policy_search,
    get_order,
    cancel_order,
    change_size,
    escalate_to_human,
)

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

# ── Tool 1: policy_search ─────────────────────────────────────────────────────
print("\n[Tool 1: policy_search]")

r = policy_search(query="how do I return an item")
check("returns 'query' key",  "query"  in r)
check("returns 'chunks' key", "chunks" in r)
check("returns 3 chunks",     len(r["chunks"]) == 3, f"got {len(r['chunks'])}")
check("each chunk has 'content'", all("content" in c for c in r["chunks"]))
check("each chunk has 'source'",  all("source"  in c for c in r["chunks"]))
check("each chunk has 'score'",   all("score"   in c for c in r["chunks"]))
print(f"    Sample source: {r['chunks'][0]['source']}")

# ── Tool 2: get_order ─────────────────────────────────────────────────────────
print("\n[Tool 2: get_order]")

# Happy path
r = get_order(order_id="ORD9001", customer_id="C001")
check("ORD9001 found",                    r["found"] is True)
check("ORD9001 has correct customer",     r["order"]["customer_id"] == "C001")
check("ORD9001 status is 'processing'",   r["order"]["status"] == "processing")
check("ORD9001 has product_name",         bool(r["order"]["product_name"]))

# Wrong customer
r = get_order(order_id="ORD9001", customer_id="C999")
check("wrong customer returns found=False", r["found"] is False)
check("wrong customer returns error msg",   "error" in r)

# Non-existent order
r = get_order(order_id="ORD0000")
check("missing order returns found=False",  r["found"] is False)

# Shipped order lookup (no mutation)
r = get_order(order_id="ORD9002", customer_id="C002")
check("ORD9002 found",                    r["found"] is True)
check("ORD9002 status is 'shipped'",      r["order"]["status"] == "shipped")
check("ORD9002 has tracking number",      bool(r["order"]["tracking_number"]))

# ── Tool 3: cancel_order ──────────────────────────────────────────────────────
print("\n[Tool 3: cancel_order]")

# Guard: shipped order cannot be cancelled
r = cancel_order(order_id="ORD9002", customer_id="C002")
check("shipped order cancel blocked",     r["success"] is False)
check("shipped order error mentions status", "shipped" in r["error"].lower())

# Guard: delivered order cannot be cancelled
r = cancel_order(order_id="ORD9003", customer_id="C003")
check("delivered order cancel blocked",   r["success"] is False)

# Guard: wrong customer
r = cancel_order(order_id="ORD9004", customer_id="C999")
check("wrong customer cancel blocked",    r["success"] is False)

# Guard: non-existent order
r = cancel_order(order_id="ORD0000", customer_id="C001")
check("missing order cancel blocked",     r["success"] is False)

# Happy path: cancel a processing order (use ORD9004 so ORD9001 stays for change_size test)
r = cancel_order(order_id="ORD9004", customer_id="C004")
check("processing order cancelled",       r["success"] is True, str(r))
check("new_status is 'cancelled'",        r.get("new_status") == "cancelled")
check("response has message",             bool(r.get("message")))

# Verify DB was updated
from mcp_server.server import get_order as _go
r2 = _go(order_id="ORD9004", customer_id="C004")
check("DB reflects cancelled status",     r2["order"]["status"] == "cancelled")

# Guard: already-cancelled order cannot be cancelled again
r = cancel_order(order_id="ORD9004", customer_id="C004")
check("already-cancelled order blocked",  r["success"] is False)

# ── Tool 4: change_size ───────────────────────────────────────────────────────
print("\n[Tool 4: change_size]")

# Guard: shipped order
r = change_size(order_id="ORD9002", customer_id="C002", new_size="34")
check("shipped order size change blocked",  r["success"] is False)
check("shipped order error mentions status", "shipped" in r["error"].lower())

# Guard: wrong customer
r = change_size(order_id="ORD9001", customer_id="C999", new_size="L")
check("wrong customer size change blocked", r["success"] is False)

# Guard: invalid size
r = change_size(order_id="ORD9001", customer_id="C001", new_size="XXXL")
check("invalid size blocked",               r["success"] is False)
check("invalid size error lists available", "available" in r["error"].lower())

# Happy path: ORD9001 is Classic White Tee (P001), sizes: XS,S,M,L,XL,XXL
r = change_size(order_id="ORD9001", customer_id="C001", new_size="L")
check("valid size change succeeds",         r["success"] is True, str(r))
check("old_size is 'M'",                    r.get("old_size") == "M")
check("new_size is 'L'",                    r.get("new_size") == "L")
check("response has message",               bool(r.get("message")))

# Verify DB was updated
r2 = _go(order_id="ORD9001", customer_id="C001")
check("DB reflects new size 'L'",           r2["order"]["size"] == "L")

# ── Tool 5: escalate_to_human ─────────────────────────────────────────────────
print("\n[Tool 5: escalate_to_human]")

r = escalate_to_human(
    customer_id="C005",
    reason="Customer wants refund for cancelled order",
    conversation_summary="Customer C005 asked about order ORD9005 which was already cancelled. Wants full refund confirmation.",
    order_id="ORD9005",
)
check("escalation succeeds",              r["success"] is True)
check("ticket_id returned",               bool(r.get("ticket_id")))
check("ticket_id starts with TKT-",       r["ticket_id"].startswith("TKT-"))
check("message mentions ticket ID",       r["ticket_id"] in r["message"])
check("estimated_response returned",      bool(r.get("estimated_response")))
print(f"    Ticket created: {r['ticket_id']}")

# Escalation without order_id
r2 = escalate_to_human(
    customer_id="C006",
    reason="General billing question",
    conversation_summary="Customer has a question about a charge on their account.",
)
check("escalation without order_id works", r2["success"] is True)
check("second ticket has different ID",    r2["ticket_id"] != r["ticket_id"])

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "-" * 50)
if failures:
    print(f"[FAILED] {len(failures)} check(s) failed: {failures}")
    sys.exit(1)
else:
    print("[PASSED] All Phase 3 checks passed -- ready for Phase 4!")
print()
