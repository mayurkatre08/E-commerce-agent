"""
agents/escalation_agent.py
Escalates the conversation to a human agent via the escalate_to_human MCP tool.
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


def _build_summary(state: AgentState) -> str:
    lines = []
    for m in state["messages"][-6:]:
        role = "Customer" if m.type == "human" else "Agent"
        lines.append(f"{role}: {m.content[:120]}")
    return "\n".join(lines) if lines else "No prior conversation."


async def escalation_agent_node(state: AgentState, tools: dict) -> AgentState:
    customer_id = state.get("customer_id") or "UNKNOWN"
    order_id    = state.get("order_id")
    last_human  = next((m for m in reversed(state["messages"]) if m.type == "human"), None)
    reason      = last_human.content[:200] if last_human else "Customer requested escalation."
    summary     = _build_summary(state)

    raw    = await tools["escalate_to_human"].ainvoke({
        "customer_id":          customer_id,
        "reason":               reason,
        "conversation_summary": summary,
        "order_id":             order_id,
    })
    result = _parse(raw)

    if result.get("success"):
        ticket_id = result.get("ticket_id", "N/A")
        eta       = result.get("estimated_response", "2-4 business hours")
        reply = (
            f"I've escalated your case to a human support agent.\n"
            f"Your ticket ID is: {ticket_id}\n"
            f"Expected response time: {eta}\n"
            f"Please keep this ticket ID for reference."
        )
    else:
        reply = "I'm connecting you with a human support agent. Please hold on while we transfer your case."

    return {**state, "messages": state["messages"] + [AIMessage(content=reply)],
            "escalated": True, "resolved": True}
