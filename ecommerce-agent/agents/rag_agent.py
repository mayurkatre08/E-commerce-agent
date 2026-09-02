"""
agents/rag_agent.py
Answers policy questions using the policy_search MCP tool.
"""

import json
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from agents.state import AgentState
from agents.llm import get_llm

SYSTEM_PROMPT = """You are a helpful e-commerce customer support agent specialising in store policies.
You have been given relevant policy excerpts below. Answer the customer's question
clearly and concisely using ONLY the provided context.
If the context does not contain enough information, say so honestly.
Do not make up policies."""


async def rag_agent_node(state: AgentState, tools: dict) -> AgentState:
    last_human = next(
        (m for m in reversed(state["messages"]) if m.type == "human"), None
    )
    query = last_human.content if last_human else "policy question"

    raw_result = await tools["policy_search"].ainvoke({"query": query})

    try:
        if isinstance(raw_result, list):
            text = next((b["text"] for b in raw_result if b.get("type") == "text"), "{}")
            data = json.loads(text)
        elif isinstance(raw_result, str):
            data = json.loads(raw_result)
        else:
            data = raw_result
        chunks  = data.get("chunks", [])
        context = "\n\n---\n\n".join(
            f"[Source: {c['source']}]\n{c['content']}" for c in chunks
        )
    except Exception:
        context = str(raw_result)

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Policy context:\n{context}\n\nCustomer question: {query}"),
    ])

    return {**state, "messages": state["messages"] + [AIMessage(content=response.content)], "resolved": True}
