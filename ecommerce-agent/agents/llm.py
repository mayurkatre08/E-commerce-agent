"""
agents/llm.py
Returns the correct LLM based on environment.
- Real Groq credentials -> ChatGroq
- Placeholder creds -> SmartFakeChatModel (dev/test, intent-aware)
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class _SmartFakeChatModel(BaseChatModel):
    """
    Dev-mode LLM: inspects message content and returns intent-correct
    responses without hitting any API.
    """

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, ChatResult

        combined = " ".join(m.content.lower() for m in messages)
        from langchain_core.messages import HumanMessage as _HM
        human_msgs = [m.content.lower() for m in messages if isinstance(m, _HM)]
        user_text = human_msgs[-1] if human_msgs else combined

        if '"intent"' in combined or "respond only with valid json" in combined:
            if any(w in user_text for w in ["cancel", "cancell"]):
                text = '{"intent": "cancel", "customer_id": "C001", "order_id": "ORD9001"}'
            elif any(w in user_text for w in ["change", "size", "resize"]):
                text = '{"intent": "change_size", "customer_id": "C004", "order_id": "ORD9004"}'
            elif any(w in user_text for w in ["status", "track", "where is", "order", "ord9"]):
                text = '{"intent": "order_lookup", "customer_id": "C002", "order_id": "ORD9002"}'
            elif any(w in user_text for w in ["human", "agent", "unacceptable", "escalat", "speak to"]):
                text = '{"intent": "escalate", "customer_id": "C005", "order_id": null}'
            else:
                text = '{"intent": "policy", "customer_id": null, "order_id": null}'
        elif "extract the following" in combined:
            if "cancel" in combined:
                text = '{"action": "cancel", "order_id": "ORD9001", "customer_id": "C001"}'
            else:
                text = '{"action": "change_size", "order_id": "ORD9004", "customer_id": "C004", "new_size": "XL"}'
        elif "policy context" in combined:
            text = "Based on our store policy, you can return items within 30 days of delivery in original condition."
        else:
            text = "I understand your request. Let me help you with that."

        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    @property
    def _llm_type(self) -> str:
        return "smart-fake-chat"


def get_llm() -> BaseChatModel:
    api_key = os.environ.get("GROQ_API_KEY", "your-groq-api-key")

    if api_key in {"", "your-groq-api-key", "your-api-key"}:
        return _SmartFakeChatModel()

    from langchain_groq import ChatGroq

    return ChatGroq(
        model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b"),
        groq_api_key=api_key,
        temperature=0,
    )
