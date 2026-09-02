"""
test_phase7.py -- Validates Phase 7: FastAPI endpoints.
Uses httpx AsyncClient + LifespanManager (no running server needed).
Run: python tests/test_phase7.py
"""

import os
import sys
import asyncio
import subprocess
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
    subprocess.run(
        [sys.executable, "data/seed_db.py"],
        capture_output=True,
        cwd=os.path.join(os.path.dirname(__file__), "..")
    )

    from httpx import AsyncClient, ASGITransport
    from asgi_lifespan import LifespanManager
    from api.main import app

    async with LifespanManager(app) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as client:

            # -- /health ---------------------------------------------------
            print("\n[GET /health]")
            r = await client.get("/health")
            check("status 200",       r.status_code == 200)
            check("status=ok",        r.json()["status"] == "ok")
            check("graph_ready=True", r.json()["graph_ready"] is True)

            # -- /order/{id} -----------------------------------------------
            print("\n[GET /order/{order_id}]")

            r = await client.get("/order/ORD9001")
            check("ORD9001 found=True",       r.json()["found"] is True)
            check("ORD9001 has order dict",   isinstance(r.json()["order"], dict))
            check("ORD9001 order_id correct", r.json()["order"]["order_id"] == "ORD9001")
            check("ORD9001 status field",     "status" in r.json()["order"])

            r = await client.get("/order/ORD9002?customer_id=C002")
            check("ORD9002 found",        r.json()["found"] is True)
            check("ORD9002 has tracking", r.json()["order"].get("tracking_number") is not None)

            r = await client.get("/order/ORD9001?customer_id=C999")
            check("wrong customer found=False", r.json()["found"] is False)
            check("wrong customer has error",   "error" in r.json())

            r = await client.get("/order/ORD0000")
            check("missing order found=False",  r.json()["found"] is False)

            # -- /chat -----------------------------------------------------
            print("\n[POST /chat]")

            # Policy
            r = await client.post("/chat", json={"message": "What is your return policy?"})
            check("policy 200",             r.status_code == 200)
            d = r.json()
            check("policy has reply",       bool(d.get("reply")))
            check("policy intent=policy",   d.get("intent") == "policy", f"got '{d.get('intent')}'")
            check("policy escalated=False", d.get("escalated") is False)
            check("policy resolved=True",   d.get("resolved") is True)
            check("policy has session_id",  bool(d.get("session_id")))
            check("policy has run_ms",      isinstance(d.get("run_ms"), float))
            print(f"  Reply: {d.get('reply','')[:80]}")

            # Order lookup
            r = await client.post("/chat", json={
                "message":     "What is the status of my order ORD9002?",
                "customer_id": "C002",
                "order_id":    "ORD9002",
                "session_id":  "test-sess-01",
            })
            check("order 200",                 r.status_code == 200)
            d = r.json()
            check("order intent=order_lookup", d.get("intent") == "order_lookup", f"got '{d.get('intent')}'")
            check("order reply has ORD9002",   "ORD9002" in d.get("reply", ""))
            check("session_id preserved",      d.get("session_id") == "test-sess-01")
            print(f"  Reply: {d.get('reply','')[:80]}")

            # Cancel
            r = await client.post("/chat", json={
                "message":     "Please cancel my order ORD9001",
                "customer_id": "C001",
                "order_id":    "ORD9001",
            })
            check("cancel 200",           r.status_code == 200)
            d = r.json()
            check("cancel intent=cancel", d.get("intent") == "cancel", f"got '{d.get('intent')}'")
            check("cancel reply ok",      any(w in d.get("reply","").lower() for w in ["cancel","refund"]))
            print(f"  Reply: {d.get('reply','')[:80]}")

            # Escalation
            r = await client.post("/chat", json={
                "message":     "I want to speak to a human agent!",
                "customer_id": "C005",
            })
            check("escalate 200",             r.status_code == 200)
            d = r.json()
            check("escalate intent=escalate", d.get("intent") == "escalate", f"got '{d.get('intent')}'")
            check("escalate escalated=True",  d.get("escalated") is True)
            check("escalate has ticket",      any(w in d.get("reply","").lower() for w in ["ticket","tkt","agent"]))
            print(f"  Reply: {d.get('reply','')[:80]}")

            # -- /metrics --------------------------------------------------
            print("\n[GET /metrics]")
            r = await client.get("/metrics")
            check("metrics 200",            r.status_code == 200)
            m = r.json()
            check("has total_runs",         "total_runs" in m)
            check("total_runs >= 4",        m["total_runs"] >= 4, f"got {m['total_runs']}")
            check("has escalation_rate",    "escalation_rate" in m)
            check("has tools",              "tools" in m)
            check("policy_search in tools", "policy_search" in m["tools"])
            check("policy_search rate=1.0", m["tools"]["policy_search"]["success_rate"] == 1.0)
            check("escalation_rate > 0",    (m["escalation_rate"] or 0) > 0)
            print(f"  Escalation rate : {m['escalation_rate']}")
            print(f"  RAG groundedness: {m['avg_rag_groundedness']}")
            print(f"  Tools tracked   : {list(m['tools'].keys())}")


asyncio.run(run_tests())

print("\n" + "-" * 50)
if failures:
    print(f"[FAILED] {len(failures)} check(s) failed: {failures}")
    sys.exit(1)
else:
    print("[PASSED] All Phase 7 checks passed -- full application complete!")
print()
