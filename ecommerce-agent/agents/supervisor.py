"""
agents/supervisor.py
Classifies user intent and extracts context (customer_id, order_id).
Routes to: rag_agent | order_agent | action_agent | escalation_agent
"""

import json
import re
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState
from agents.llm import get_llm

SYSTEM_PROMPT = """You are a customer support supervisor for an e-commerce fashion store.
Analyze the user's latest message and extract:
1. intent — one of: policy | order_lookup | cancel | change_size | escalate
2. customer_id — if mentioned (format: C001, C002, etc.), else null
3. order_id — if mentioned (format: ORD####), else null

Intent definitions:
- policy       : questions about return/shipping/sizing/payment/exchange policies
- order_lookup : asking about order status, tracking, delivery
- cancel       : wants to cancel an order
- change_size  : wants to change the size of an ordered item
- escalate     : frustrated, complex issue, explicitly asks for human agent

Respond ONLY with valid JSON, no markdown, no explanation:
{"intent": "...", "customer_id": "..." or null, "order_id": "..." or null}"""


def supervisor_node(state: AgentState) -> AgentState:
    llm = get_llm()

    # Get the last human message
    last_human = next(
        (m for m in reversed(state["messages"]) if m.type == "human"),
        None,
    )
    if last_human is None:
        return {**state, "intent": "escalate"}

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=last_human.content),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(raw)
        intent      = parsed.get("intent", "escalate")
        customer_id = parsed.get("customer_id") or state.get("customer_id")
        order_id    = parsed.get("order_id")    or state.get("order_id")
    except (json.JSONDecodeError, AttributeError):
        intent      = "escalate"
        customer_id = state.get("customer_id")
        order_id    = state.get("order_id")

    # Supervisor only updates routing fields — does NOT append to messages
    return {
        "intent":      intent,
        "customer_id": customer_id,
        "order_id":    order_id,
        "escalated":   state.get("escalated", False),
        "resolved":    state.get("resolved",  False),
    }


def route_intent(state: AgentState) -> str:
    """Conditional edge: maps intent → next node name."""
    intent = state.get("intent", "escalate")
    return {
        "policy":       "rag_agent",
        "order_lookup": "order_agent",
        "cancel":       "action_agent",
        "change_size":  "action_agent",
        "escalate":     "escalation_agent",
    }.get(intent, "escalation_agent")
