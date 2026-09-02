"""
ui/app.py
Streamlit chat interface for the e-commerce support agent.

Run:
  streamlit run ui/app.py
  (API must be running on http://localhost:8000)
"""

import requests
import streamlit as st

API_URL = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="E-Commerce Support Agent",
    page_icon="🛍️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------

if "messages"    not in st.session_state: st.session_state.messages    = []
if "session_id"  not in st.session_state: st.session_state.session_id  = None
if "escalated"   not in st.session_state: st.session_state.escalated   = False
if "last_intent" not in st.session_state: st.session_state.last_intent = None

# ---------------------------------------------------------------------------
# Sidebar — context inputs + metrics
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🛍️ Support Agent")
    st.markdown("---")

    st.subheader("Your Details")
    customer_id = st.text_input("Customer ID", placeholder="e.g. C001")
    order_id    = st.text_input("Order ID",    placeholder="e.g. ORD9001")

    st.markdown("---")

    # Quick-action buttons
    st.subheader("Quick Actions")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Return Policy"):
            st.session_state["_prefill"] = "What is your return policy?"
    with col2:
        if st.button("Track Order"):
            st.session_state["_prefill"] = f"What is the status of my order {order_id}?" if order_id else "What is the status of my order?"

    col3, col4 = st.columns(2)
    with col3:
        if st.button("Cancel Order"):
            st.session_state["_prefill"] = f"Please cancel my order {order_id}." if order_id else "I want to cancel my order."
    with col4:
        if st.button("Human Agent"):
            st.session_state["_prefill"] = "I want to speak to a human agent."

    st.markdown("---")

    # Live metrics
    st.subheader("Live Metrics")
    if st.button("Refresh Metrics"):
        try:
            r = requests.get(f"{API_URL}/metrics", timeout=3)
            if r.status_code == 200:
                m = r.json()
                st.metric("Total Runs",      m.get("total_runs", 0))
                st.metric("Escalation Rate", f"{(m.get('escalation_rate') or 0)*100:.1f}%")
                st.metric("RAG Groundedness",f"{(m.get('avg_rag_groundedness') or 0)*100:.1f}%")
                tools = m.get("tools", {})
                if "policy_search" in tools:
                    t = tools["policy_search"]
                    st.metric("policy_search p95", f"{t.get('p95_latency_ms', 'N/A')} ms")
            else:
                st.warning("Could not fetch metrics.")
        except Exception:
            st.warning("API not reachable.")

    st.markdown("---")
    if st.button("Clear Chat"):
        st.session_state.messages    = []
        st.session_state.session_id  = None
        st.session_state.escalated   = False
        st.session_state.last_intent = None
        st.rerun()

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------

st.title("E-Commerce Customer Support")

# Status banner
if st.session_state.escalated:
    st.error("🔴 This conversation has been escalated to a human agent.")
elif st.session_state.last_intent:
    intent_colors = {
        "policy":       "🟢",
        "order_lookup": "🔵",
        "cancel":       "🟠",
        "change_size":  "🟡",
        "escalate":     "🔴",
    }
    icon = intent_colors.get(st.session_state.last_intent, "⚪")
    st.info(f"{icon} Last intent: **{st.session_state.last_intent}**")

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Pre-fill from quick-action buttons
prefill = st.session_state.pop("_prefill", None)

# Chat input
user_input = st.chat_input("How can I help you today?", disabled=st.session_state.escalated)

if prefill and not user_input:
    user_input = prefill

if user_input:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Call API
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                payload = {
                    "message":     user_input,
                    "customer_id": customer_id or None,
                    "order_id":    order_id    or None,
                    "session_id":  st.session_state.session_id,
                }
                resp = requests.post(f"{API_URL}/chat", json=payload, timeout=30)

                if resp.status_code == 200:
                    data = resp.json()
                    reply = data["reply"]

                    # Update session state
                    st.session_state.session_id  = data["session_id"]
                    st.session_state.escalated   = data["escalated"]
                    st.session_state.last_intent = data["intent"]

                    st.markdown(reply)
                    st.caption(f"Intent: `{data['intent']}` | {data['run_ms']:.0f}ms | Session: `{data['session_id']}`")

                    st.session_state.messages.append({"role": "assistant", "content": reply})

                    if data["escalated"]:
                        st.rerun()
                else:
                    err = f"API error {resp.status_code}: {resp.text}"
                    st.error(err)
                    st.session_state.messages.append({"role": "assistant", "content": err})

            except requests.exceptions.ConnectionError:
                msg = "Cannot connect to the API. Make sure `uvicorn api.main:app --port 8000` is running."
                st.error(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
            except Exception as e:
                msg = f"Unexpected error: {e}"
                st.error(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
