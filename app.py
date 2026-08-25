"""
app.py
------
Streamlit chat UI for the Skylark Business Intelligence Agent.

Uses Groq's free LLM API (no credit card needed) — get a key at
https://console.groq.com/keys.

Deploy for free on Streamlit Community Cloud (share.streamlit.io):
  1. Push this repo to GitHub.
  2. On share.streamlit.io: New app -> pick the repo -> main file "app.py".
  3. In the app's Settings -> Secrets, paste:
       GROQ_API_KEY = "gsk_..."
       MONDAY_API_TOKEN = "..."
       MONDAY_WORK_ORDERS_BOARD_ID = "123456"
       MONDAY_DEALS_BOARD_ID = "123457"
  4. Deploy. You get a public https://<name>.streamlit.app link — that's
     the "Hosted Prototype" deliverable.

Run locally:
    streamlit run app.py
"""
import os
from dotenv import load_dotenv
import streamlit as st

# Load environment variables from .env if present (for local execution)
load_dotenv()

from agent.core import BIAgent

st.set_page_config(page_title="Skylark BI Agent", page_icon="📊", layout="wide")


def get_secret(key: str) -> str | None:
    # Works both with Streamlit secrets.toml and plain env vars (local dev / other hosts)
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key)


st.title("📊 Skylark BI Agent")
st.caption(
    "Ask founder-level questions about pipeline, revenue, and operations. "
    "Data is pulled live from the Work Orders and Deals boards on monday.com."
)

missing = [
    k for k in ["GROQ_API_KEY", "MONDAY_API_TOKEN", "MONDAY_WORK_ORDERS_BOARD_ID", "MONDAY_DEALS_BOARD_ID"]
    if not get_secret(k)
]
if missing:
    st.error(
        "Missing configuration: " + ", ".join(missing) +
        ". Set these in Streamlit secrets (or as env vars if running locally). "
        "See README.md."
    )
    st.stop()

if "agent" not in st.session_state:
    st.session_state.agent = BIAgent(
        groq_api_key=get_secret("GROQ_API_KEY"),
        monday_api_token=get_secret("MONDAY_API_TOKEN"),
        work_orders_board_id=get_secret("MONDAY_WORK_ORDERS_BOARD_ID"),
        deals_board_id=get_secret("MONDAY_DEALS_BOARD_ID"),
    )
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": (
            "Hi, I'm the Skylark BI agent. I can answer questions like:\n\n"
            "- *How's our pipeline looking for the Mining sector this quarter?*\n"
            "- *What's our total receivable outstanding right now?*\n"
            "- *Give me a leadership update on Powerline vs Renewables.*\n"
            "- *How reliable is this data right now?*"
        )}
    ]

with st.sidebar:
    st.subheader("Session")
    if st.button("🔄 New conversation"):
        st.session_state.agent.reset()
        st.session_state.messages = st.session_state.messages[:1]
        st.rerun()
    show_debug = st.checkbox("Show tool calls (debug)", value=False)
    st.caption("Boards refresh from monday.com every ~2 minutes (cached) to stay responsive.")

    st.markdown("---")
    st.subheader("💡 Leadership Quick Prompts")
    quick_prompts = [
        "Give me a leadership update comparing Powerline and Renewables.",
        "What is our revenue collection rate and total receivable outstanding?",
        "How is our sales pipeline looking for Mining vs Construction?",
        "Give me an executive breakdown across all business sectors.",
        "How reliable is our data right now? Any caveats?",
    ]
    for qp in quick_prompts:
        if st.button(qp, key=f"btn_{qp}"):
            st.session_state["queued_prompt"] = qp
            st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

active_prompt = st.chat_input("Ask a business question...")
if not active_prompt and "queued_prompt" in st.session_state:
    active_prompt = st.session_state.pop("queued_prompt")

if active_prompt:
    st.session_state.messages.append({"role": "user", "content": active_prompt})
    with st.chat_message("user"):
        st.markdown(active_prompt)

    with st.chat_message("assistant"):
        with st.spinner("Querying monday.com and analyzing..."):
            try:
                result = st.session_state.agent.ask(active_prompt)
                st.markdown(result["reply"])
                if show_debug and result["tool_calls"]:
                    with st.expander("Tool calls this turn"):
                        st.json(result["tool_calls"])
                st.session_state.messages.append({"role": "assistant", "content": result["reply"]})
            except Exception as e:
                err = f"Something went wrong querying monday.com or LLM: `{e}`"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})
