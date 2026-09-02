"""
agents/order_agent.py
Retrieves and presents order details using the get_order MCP tool.
"""

import json
from langchain_core.messages import AIMessage
from agents.state import AgentState


def _parse(raw) -> dict:
    try:
        if isinstance(raw, list):
            text = next((b["text"] for b in raw if b.get("type") == "text"), "{}")
            return json.loads(text)
        if isinstance(raw, str):
            return json.loads(raw)
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


async def order_agent_node(state: AgentState, tools: dict) -> AgentState:
    order_id    = state.get("order_id")
    customer_id = state.get("customer_id")

    if not order_id:
        reply = "I'd be happy to look up your order! Could you please provide your order ID? (e.g. ORD1234)"
        return {**state, "messages": state["messages"] + [AIMessage(content=reply)], "resolved": False}

    raw    = await tools["get_order"].ainvoke({"order_id": order_id, "customer_id": customer_id})
    result = _parse(raw)

    if not result.get("found"):
        reply = f"I wasn't able to find that order. {result.get('error', 'Order not found.')}"
    else:
        o        = result["order"]
        tracking = f"\n  Tracking : {o['tracking_number']}" if o.get("tracking_number") else ""
        reply = (
            f"Here are the details for order {o['order_id']}:\n"
            f"  Product : {o['product_name']} (Size: {o['size']})\n"
            f"  Quantity: {o['quantity']}  |  Total: ${o['total_price']}\n"
            f"  Status  : {o['status'].upper()}\n"
            f"  Ordered : {o['created_at'][:10]}"
            f"{tracking}"
        )

    return {**state, "messages": state["messages"] + [AIMessage(content=reply)], "resolved": True}
