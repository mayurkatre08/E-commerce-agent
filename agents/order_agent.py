"""
agents/order_agent.py
Retrieves and presents customer-owned orders using MCP tools.
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
        raw = await tools["list_orders"].ainvoke({"customer_id": customer_id})
        result = _parse(raw)
        orders = result.get("orders", [])
        if not orders:
            reply = result.get("error", "I could not find any orders for your account.")
        else:
            lines = ["Here are all of your orders. Tell me which order ID you would like to manage:"]
            for order in orders:
                tracking = f" | Tracking: {order['tracking_number']}" if order.get("tracking_number") else ""
                lines.append(
                    f"- {order['order_id']}: {order['product_name']} | "
                    f"Size {order['size']} | Qty {order['quantity']} | "
                    f"${order['total_price']:.2f} | {order['status'].upper()}{tracking}"
                )
            reply = "\n".join(lines)
        return {**state, "messages": state["messages"] + [AIMessage(content=reply)], "resolved": True}

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
