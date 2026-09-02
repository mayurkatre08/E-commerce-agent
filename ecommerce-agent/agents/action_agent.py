"""
agents/action_agent.py
Handles destructive actions: cancel_order and change_size.
"""

import json
import re
from langchain_core.messages import SystemMessage, AIMessage
from agents.state import AgentState
from agents.llm import get_llm

EXTRACT_PROMPT = """Extract the following from the customer message. Respond ONLY with JSON, no markdown.
For cancel: {{"action": "cancel", "order_id": "...", "customer_id": "..."}}
For size change: {{"action": "change_size", "order_id": "...", "customer_id": "...", "new_size": "..."}}
If any field is missing use null.
Customer message: {message}"""


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


async def action_agent_node(state: AgentState, tools: dict) -> AgentState:
    intent      = state.get("intent", "cancel")
    order_id    = state.get("order_id")
    customer_id = state.get("customer_id")
    new_size    = None

    last_human = next((m for m in reversed(state["messages"]) if m.type == "human"), None)
    user_msg   = last_human.content if last_human else ""

    # Try to extract missing fields via LLM
    if not order_id or not customer_id:
        llm  = get_llm()
        resp = llm.invoke([SystemMessage(content=EXTRACT_PROMPT.format(message=user_msg))])
        raw  = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.content.strip(), flags=re.MULTILINE)
        try:
            extracted   = json.loads(raw)
            order_id    = order_id    or extracted.get("order_id")
            customer_id = customer_id or extracted.get("customer_id")
            new_size    = extracted.get("new_size")
        except Exception:
            pass

    # Extract new_size from message for change_size if not yet found
    if intent == "change_size" and not new_size:
        m = re.search(r"\b(XS|S|M|L|XL|XXL|\d{2})\b", user_msg, re.IGNORECASE)
        new_size = m.group(1).upper() if m else None

    if not order_id:
        return {**state, "messages": state["messages"] + [AIMessage(
            content="Could you please provide your order ID? (e.g. ORD1234)"
        )], "resolved": False}

    if not customer_id:
        return {**state, "messages": state["messages"] + [AIMessage(
            content="Could you please provide your customer ID? (e.g. C001)"
        )], "resolved": False}

    if intent == "cancel":
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
