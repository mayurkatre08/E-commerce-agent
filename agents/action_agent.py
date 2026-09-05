"""
agents/action_agent.py
Handles customer order actions: request_return, cancel_order, and change_size.
"""

import re
from langchain_core.messages import AIMessage
from agents.state import AgentState
ORDER_ID_PATTERN = re.compile(r"\bORD\d+\b", re.IGNORECASE)


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


def _format_order_choices(orders: list) -> str:
    lines = ["Here are all of your orders. Tell me which order ID you would like to manage:"]
    for order in orders:
        tracking = f" | Tracking: {order['tracking_number']}" if order.get("tracking_number") else ""
        lines.append(
            f"- {order['order_id']}: {order['product_name']} | "
            f"Size {order['size']} | Qty {order['quantity']} | "
            f"${order['total_price']:.2f} | {order['status'].upper()}{tracking}"
        )
    return "\n".join(lines)


async def action_agent_node(state: AgentState, tools: dict) -> AgentState:
    intent      = state.get("intent", "cancel")
    order_id    = state.get("order_id")
    customer_id = state.get("customer_id")
    new_size    = None

    last_human = next((m for m in reversed(state["messages"]) if m.type == "human"), None)
    user_msg   = last_human.content if last_human else ""

    # Only accept an order ID explicitly supplied by the customer or session.
    if not order_id:
        match = ORDER_ID_PATTERN.search(user_msg)
        order_id = match.group(0).upper() if match else None

    # Extract new_size from message for change_size if not yet found
    if intent == "change_size" and not new_size:
        m = re.search(r"\b(XS|S|M|L|XL|XXL|\d{2})\b", user_msg, re.IGNORECASE)
        new_size = m.group(1).upper() if m else None

    if not order_id:
        if "list_orders" in tools:
            result = _parse(await tools["list_orders"].ainvoke({"customer_id": customer_id}))
            orders = result.get("orders", [])
            reply = _format_order_choices(orders) if orders else result.get(
                "error", "I could not find any orders for your account."
            )
            return {**state, "messages": state["messages"] + [AIMessage(content=reply)], "resolved": False}
        return {**state, "messages": state["messages"] + [AIMessage(
            content="Could you please provide your order ID? (e.g. ORD1234)"
        )], "resolved": False}

    if intent == "return":
        raw = await tools["request_return"].ainvoke({"order_id": order_id, "customer_id": customer_id})
        result = _parse(raw)
        reply = result.get("message") if result.get("success") else f"Unable to request the return: {result.get('error', 'Unknown error.')}"

    elif intent == "cancel":
        raw    = await tools["cancel_order"].ainvoke({"order_id": order_id, "customer_id": customer_id})
        result = _parse(raw)
        reply  = result.get("message") if result.get("success") else f"Unable to cancel: {result.get('error', 'Unknown error.')}"

    elif intent == "change_size":
        if not new_size:
            return {**state, "messages": state["messages"] + [AIMessage(
                content="What size would you like to change to? (e.g. M, L, XL, 32)"
            )], "resolved": False}
        raw    = await tools["change_size"].ainvoke({"order_id": order_id, "customer_id": customer_id, "new_size": new_size})
        result = _parse(raw)
        reply  = result.get("message") if result.get("success") else f"Unable to change size: {result.get('error', 'Unknown error.')}"
    else:
        reply = "I'm not sure what action you'd like to take. Could you clarify?"

    return {**state, "messages": state["messages"] + [AIMessage(content=reply)],
            "order_id": order_id, "customer_id": customer_id, "resolved": True}
