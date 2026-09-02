"""
agents/state.py
Shared state schema for the LangGraph multi-agent workflow.
"""

from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # Full conversation history — add_messages merges lists automatically
    messages:    Annotated[list[BaseMessage], add_messages]
    # Extracted context — set by supervisor, read by sub-agents
    customer_id: Optional[str]
    order_id:    Optional[str]
    intent:      Optional[str]   # "policy" | "order_lookup" | "cancel" | "change_size" | "escalate"
    # Terminal flags
    escalated:   bool
    resolved:    bool
