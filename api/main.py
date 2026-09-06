"""
api/main.py
FastAPI backend for the e-commerce support agent.

Endpoints:
  POST /chat              -- run the agent for one conversation turn
  GET  /order/{order_id}  -- direct order lookup (no agent)
  GET  /metrics           -- current observability report
  GET  /health            -- liveness check

Run:
  uvicorn api.main:app --reload --port 8000
"""

import os
import sys
import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp_client.client import get_mcp_tools
from graph.workflow import build_graph
from observability.instrumented_workflow import instrument_tools, run_with_observability
from observability.metrics import metrics
from observability.tracer import trace_summary
from api.auth import create_access_token, customer_exists, get_authenticated_customer

# ---------------------------------------------------------------------------
# App state — graph is built once at startup and reused
# ---------------------------------------------------------------------------

_graph      = None
_mcp_ctx    = None   # holds the async context manager open
_sessions   = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the graph once on startup, tear down MCP on shutdown."""
    global _graph, _mcp_ctx

    print("[API] Starting up — connecting to MCP server...")
    trace_summary()

    _mcp_ctx = get_mcp_tools()
    raw_tools = await _mcp_ctx.__aenter__()
    tools     = instrument_tools(raw_tools)
    _graph    = build_graph(tools)

    print(f"[API] Graph ready with {len(raw_tools)} tools.")
    yield

    print("[API] Shutting down — closing MCP connection...")
    await _mcp_ctx.__aexit__(None, None, None)


app = FastAPI(
    title="E-Commerce Support Agent",
    description="Agentic customer support powered by LangGraph + MCP",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message:     str
    order_id:    Optional[str] = None
    session_id:  Optional[str] = None

class LoginRequest(BaseModel):
    customer_id: str
    email: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer_id: str

class ChatResponse(BaseModel):
    reply:       str
    intent:      Optional[str]
    escalated:   bool
    resolved:    bool
    session_id:  str
    run_ms:      float

class OrderResponse(BaseModel):
    found:       bool
    order:       Optional[dict] = None
    error:       Optional[str]  = None

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "graph_ready": _graph is not None}


@app.post("/auth/token", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Issue a customer JWT after validating the demo customer's credentials."""
    if not customer_exists(req.customer_id, req.email):
        raise HTTPException(status_code=401, detail="Invalid customer credentials")
    return TokenResponse(access_token=create_access_token(req.customer_id), customer_id=req.customer_id)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, customer_id: str = Depends(get_authenticated_customer)):
    if _graph is None:
        raise HTTPException(status_code=503, detail="Agent not ready yet.")

    session_id = req.session_id or str(uuid.uuid4())[:8]
    session = _sessions.get(session_id)
    if session and session["customer_id"] != customer_id:
        raise HTTPException(status_code=403, detail="Session belongs to another customer")

    previous_messages = session["messages"] if session else []
    selected_order_id = req.order_id or (session.get("order_id") if session else None)

    result = await run_with_observability(
        _graph,
        user_message=req.message,
        customer_id=customer_id,
        order_id=selected_order_id,
        session_id=session_id,
        conversation_history=previous_messages,
    )

    _sessions[session_id] = {
        "customer_id": customer_id,
        "messages": result["messages"],
        "order_id": result.get("order_id"),
    }

    # Last message is the agent reply
    reply = result["messages"][-1].content

    return ChatResponse(
        reply=reply,
        intent=result.get("intent"),
        escalated=result.get("escalated", False),
        resolved=result.get("resolved", False),
        session_id=session_id,
        run_ms=result.get("_run_ms", 0.0),
    )


@app.get("/order/{order_id}", response_model=OrderResponse)
async def get_order_endpoint(order_id: str, customer_id: str = Depends(get_authenticated_customer)):
    """Direct order lookup — bypasses the agent graph."""
    import sqlite3
    db_path = os.path.join(os.path.dirname(__file__), "..", "db", "ecommerce.db")
    conn    = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur     = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE order_id = ? AND customer_id = ?", (order_id, customer_id))
    row     = cur.fetchone()
    conn.close()

    if row is None:
        return OrderResponse(found=False, error=f"Order {order_id} not found for this customer.")

    order = dict(row)
    return OrderResponse(found=True, order=order)


@app.get("/metrics")
async def get_metrics():
    """Return current observability metrics report."""
    return metrics.report()
