"""
graph/workflow.py
LangGraph StateGraph wiring the supervisor and all sub-agents.
All sub-agent nodes are async — use graph.ainvoke() to run.
"""

from functools import partial
from langgraph.graph import StateGraph, END

from agents.state import AgentState
from agents.supervisor import supervisor_node, route_intent
from agents.rag_agent import rag_agent_node
from agents.order_agent import order_agent_node
from agents.action_agent import action_agent_node
from agents.escalation_agent import escalation_agent_node


def build_graph(tools: list):
    """
    Build and compile the LangGraph workflow.

    Args:
        tools: list of LangChain BaseTool instances from MCP client

    Returns:
        Compiled LangGraph runnable (use .ainvoke() for async execution)
    """
    tool_map = {t.name: t for t in tools}

    # Bind tool_map into each async agent node
    rag_node        = partial(rag_agent_node,        tools=tool_map)
    order_node      = partial(order_agent_node,      tools=tool_map)
    action_node     = partial(action_agent_node,     tools=tool_map)
    escalation_node = partial(escalation_agent_node, tools=tool_map)

    builder = StateGraph(AgentState)

    builder.add_node("supervisor",       supervisor_node)
    builder.add_node("rag_agent",        rag_node)
    builder.add_node("order_agent",      order_node)
    builder.add_node("action_agent",     action_node)
    builder.add_node("escalation_agent", escalation_node)

    builder.set_entry_point("supervisor")

    builder.add_conditional_edges(
        "supervisor",
        route_intent,
        {
            "rag_agent":        "rag_agent",
            "order_agent":      "order_agent",
            "action_agent":     "action_agent",
            "escalation_agent": "escalation_agent",
        },
    )

    builder.add_edge("rag_agent",        END)
    builder.add_edge("order_agent",      END)
    builder.add_edge("action_agent",     END)
    builder.add_edge("escalation_agent", END)

    return builder.compile()


def get_initial_state(
    user_message: str,
    customer_id: str = None,
    order_id: str = None,
) -> AgentState:
    from langchain_core.messages import HumanMessage
    return AgentState(
        messages=[HumanMessage(content=user_message)],
        customer_id=customer_id,
        order_id=order_id,
        intent=None,
        escalated=False,
        resolved=False,
    )
