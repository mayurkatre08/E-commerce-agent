"""
mcp_server/server.py
FastMCP server exposing 5 tools for the e-commerce support agent.
Uses native mcp.server.fastmcp (mcp 1.x) — compatible with langchain-mcp-adapters.

Tools:
  1. policy_search       -- RAG over policy docs (ChromaDB)
  2. get_order           -- fetch order details from SQLite
  3. cancel_order        -- cancel an order (guard: status must be 'processing')
  4. change_size         -- change order size (guard: status must be 'processing')
  5. escalate_to_human   -- create a support ticket and hand off

Run standalone:
  python mcp_server/server.py
"""

import os
import sys
import sqlite3
import uuid
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp.server.fastmcp import FastMCP

from vectorstore.ingest import load_vectorstore

# ---------------------------------------------------------------------------
# Shared resources
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "ecommerce.db")

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

_vectorstore = None

def _get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = load_vectorstore()
    return _vectorstore

_tickets: dict = {}

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="ecommerce-support",
    instructions=(
        "Backend tool server for an e-commerce customer support agent. "
        "Use these tools to answer policy questions, look up orders, perform "
        "safe order mutations, and escalate to human agents when needed."
    ),
)

# ---------------------------------------------------------------------------
# Tool 1: policy_search
# ---------------------------------------------------------------------------

@mcp.tool()
def policy_search(query: str) -> dict:
    """
    Search the policy knowledge base and return the top relevant chunks.
    Use for questions about returns, shipping, sizing, cancellations, payments, exchanges.

    Args:
        query: Natural language question about store policies.
    """
    vs = _get_vectorstore()
    results = vs.similarity_search_with_score(query, k=3)
    chunks = [
        {
            "content": doc.page_content,
            "source":  os.path.basename(doc.metadata.get("source", "unknown")),
            "score":   round(float(score), 4),
        }
        for doc, score in results
    ]
    return {"query": query, "chunks": chunks}


# ---------------------------------------------------------------------------
# Tool 2: get_order
# ---------------------------------------------------------------------------

@mcp.tool()
def get_order(order_id: str, customer_id: Optional[str] = None) -> dict:
    """
    Retrieve full order details from the database.
    Optionally verify the order belongs to the given customer.

    Args:
        order_id:    Order ID, e.g. ORD9001.
        customer_id: Customer ID for ownership verification, e.g. C001.
    """
    conn = _get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row  = cur.fetchone()
    conn.close()

    if row is None:
        return {"found": False, "error": f"Order {order_id} not found."}

    order = dict(row)
    if customer_id and order["customer_id"] != customer_id:
        return {"found": False, "error": f"Order {order_id} does not belong to customer {customer_id}."}

    return {"found": True, "order": order}


# ---------------------------------------------------------------------------
# Tool 3: cancel_order
# ---------------------------------------------------------------------------

@mcp.tool()
def cancel_order(order_id: str, customer_id: str) -> dict:
    """
    Cancel an order. Only allowed when order status is 'processing'.
    Orders that are 'shipped' or 'delivered' cannot be cancelled.

    Args:
        order_id:    Order ID to cancel.
        customer_id: Customer ID — must match order owner.
    """
    conn = _get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row  = cur.fetchone()

    if row is None:
        conn.close()
        return {"success": False, "error": f"Order {order_id} not found."}

    if row["customer_id"] != customer_id:
        conn.close()
        return {"success": False, "error": "Order does not belong to this customer."}

    if row["status"] != "processing":
        conn.close()
        return {
            "success": False,
            "error": (
                f"Cannot cancel order {order_id} — current status is '{row['status']}'. "
                "Only 'processing' orders can be cancelled. "
                "If the order has shipped, please initiate a return instead."
            ),
        }

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "UPDATE orders SET status = 'cancelled', updated_at = ? WHERE order_id = ?",
        (now, order_id),
    )
    conn.commit()
    conn.close()

    return {
        "success":    True,
        "order_id":   order_id,
        "new_status": "cancelled",
        "message":    f"Order {order_id} has been successfully cancelled. A full refund will be issued within 3-5 business days.",
    }


# ---------------------------------------------------------------------------
# Tool 4: change_size
# ---------------------------------------------------------------------------

@mcp.tool()
def change_size(order_id: str, customer_id: str, new_size: str) -> dict:
    """
    Change the size of an ordered item. Only allowed when order status is 'processing'.
    Validates the new size against the product's available sizes.

    Args:
        order_id:    Order ID to update.
        customer_id: Customer ID — must match order owner.
        new_size:    New size, e.g. 'L', 'XL', '32', '10'.
    """
    conn = _get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    order = cur.fetchone()

    if order is None:
        conn.close()
        return {"success": False, "error": f"Order {order_id} not found."}

    if order["customer_id"] != customer_id:
        conn.close()
        return {"success": False, "error": "Order does not belong to this customer."}

    if order["status"] != "processing":
        conn.close()
        return {
            "success": False,
            "error": (
                f"Cannot change size for order {order_id} — current status is '{order['status']}'. "
                "Size changes are only allowed while the order is still processing."
            ),
        }

    cur.execute("SELECT available_sizes FROM products WHERE product_id = ?", (order["product_id"],))
    product = cur.fetchone()
    if product:
        available = [s.strip() for s in product["available_sizes"].split(",")]
        if new_size not in available:
            conn.close()
            return {
                "success": False,
                "error": f"Size '{new_size}' is not available for this product. Available sizes: {available}.",
            }

    now      = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    old_size = order["size"]
    cur.execute(
        "UPDATE orders SET size = ?, updated_at = ? WHERE order_id = ?",
        (new_size, now, order_id),
    )
    conn.commit()
    conn.close()

    return {
        "success":      True,
        "order_id":     order_id,
        "product_name": order["product_name"],
        "old_size":     old_size,
        "new_size":     new_size,
        "message":      f"Size for order {order_id} ({order['product_name']}) changed from {old_size} to {new_size}.",
    }


# ---------------------------------------------------------------------------
# Tool 5: escalate_to_human
# ---------------------------------------------------------------------------

@mcp.tool()
def escalate_to_human(
    customer_id: str,
    reason: str,
    conversation_summary: str,
    order_id: Optional[str] = None,
) -> dict:
    """
    Escalate the conversation to a human support agent and create a ticket.
    Use when the issue is complex, the customer is frustrated, or automated
    tools cannot resolve the problem.

    Args:
        customer_id:           Customer ID raising the issue.
        reason:                Short reason for escalation.
        conversation_summary:  Summary of the conversation so far.
        order_id:              Related order ID if applicable.
    """
    ticket_id  = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    _tickets[ticket_id] = {
        "ticket_id":            ticket_id,
        "customer_id":          customer_id,
        "order_id":             order_id,
        "reason":               reason,
        "conversation_summary": conversation_summary,
        "status":               "open",
        "created_at":           created_at,
    }

    return {
        "success":            True,
        "ticket_id":          ticket_id,
        "message":            (
            f"Your request has been escalated to a human support agent. "
            f"Your ticket ID is {ticket_id}. "
            f"A support agent will contact you within 2-4 business hours."
        ),
        "estimated_response": "2-4 business hours",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
