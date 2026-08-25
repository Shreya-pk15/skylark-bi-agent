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

st.set_page_config(
    page_title="Skylark Executive BI Agent",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Executive Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    /* Main Header */
    .main-header {
        background: linear-gradient(135deg, #0F172A 0%, #1E1B4B 50%, #312E81 100%);
        padding: 26px 30px;
        border-radius: 18px;
        color: white;
        margin-bottom: 24px;
        box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.3), 0 8px 10px -6px rgba(15, 23, 42, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.12);
    }
    
    .main-header h1 {
        color: #FFFFFF !important;
        font-weight: 700;
        font-size: 1.95rem;
        margin: 0 0 6px 0;
        display: flex;
        align-items: center;
        gap: 12px;
        letter-spacing: -0.5px;
    }
    
    .main-header p {
        color: #C7D2FE !important;
        font-size: 0.95rem;
        margin: 0;
        line-height: 1.5;
    }
    
    .status-badge {
        display: inline-flex;
        align-items: center;
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid rgba(16, 185, 129, 0.45);
        color: #10B981;
        padding: 5px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.6px;
    }
    
    /* KPI Ribbon Cards */
    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 16px 20px;
        text-align: left;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02), 0 1px 2px rgba(0,0,0,0.04);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.06);
    }
    
    .kpi-title {
        font-size: 0.72rem;
        text-transform: uppercase;
        color: #64748B;
        font-weight: 700;
        letter-spacing: 0.6px;
        margin-bottom: 4px;
    }
    
    .kpi-val {
        font-size: 1.25rem;
        font-weight: 800;
        color: #0F172A;
        letter-spacing: -0.3px;
    }
    
    /* Chat Message Polish */
    .stChatMessage {
        border-radius: 14px;
        margin-bottom: 12px;
        padding: 14px 18px;
        border: 1px solid #E2E8F0;
        background-color: #FFFFFF;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    
    /* Sidebar Polish */
    section[data-testid="stSidebar"] {
        background-color: #F8FAFC;
        border-right: 1px solid #E2E8F0;
    }
    
    .stButton>button {
        border-radius: 10px;
        font-weight: 600;
        border: 1px solid #CBD5E1;
        transition: all 0.2s;
    }
    .stButton>button:hover {
        border-color: #4F46E5;
        color: #4F46E5;
        background-color: #EEF2FF;
    }
</style>
""", unsafe_allow_html=True)


def get_secret(key: str) -> str | None:
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key)


missing = [
    k for k in ["GROQ_API_KEY", "MONDAY_API_TOKEN", "MONDAY_WORK_ORDERS_BOARD_ID", "MONDAY_DEALS_BOARD_ID"]
    if not get_secret(k)
]
if missing:
    st.error(
        "⚠️ Missing configuration: " + ", ".join(missing) +
        ". Set these in Streamlit Cloud Secrets (or local .env). See README.md."
    )
    st.stop()

# Header Banner
st.markdown("""
<div class="main-header">
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
        <h1>🦅 Skylark BI Decision Agent</h1>
        <span class="status-badge">● LIVE MONDAY.COM SYNC</span>
    </div>
    <p>Conversational business intelligence for founders & leadership — real-time pipeline analytics, revenue metrics, and operational performance.</p>
</div>
""", unsafe_allow_html=True)

# Executive KPI Summary Ribbon
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown("""
    <div class="kpi-card">
        <div class="kpi-title">Data Sources</div>
        <div class="kpi-val">2 Live Boards</div>
    </div>
    """, unsafe_allow_html=True)
with c2:
    st.markdown("""
    <div class="kpi-card">
        <div class="kpi-title">Tracked Sectors</div>
        <div class="kpi-val">11 Key Sectors</div>
    </div>
    """, unsafe_allow_html=True)
with c3:
    st.markdown("""
    <div class="kpi-card">
        <div class="kpi-title">Reasoning Engine</div>
        <div class="kpi-val">ReAct Tool Agent</div>
    </div>
    """, unsafe_allow_html=True)
with c4:
    st.markdown("""
    <div class="kpi-card">
        <div class="kpi-title">Data Health Guard</div>
        <div class="kpi-val">Active QA Checks</div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

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
            "👋 **Hello! I'm your Skylark BI Decision Agent.**\n\n"
            "I query our live **Work Orders** and **Deals** boards on monday.com to answer strategic questions with verified metrics:\n\n"
            "- 📈 **Pipeline:** *'How is our sales pipeline looking for Mining vs Construction?'*\n"
            "- 💰 **Revenue & Cash:** *'What is our total receivable outstanding and collection rate?'*\n"
            "- 📊 **Leadership Briefing:** *'Give me an executive comparison between Powerline and Renewables.'*\n"
            "- 🛡️ **Data Health:** *'How reliable is this data right now? Any gaps?'*"
        )}
    ]

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/isometric/100/combo-chart.png", width=60)
    st.subheader("Executive Control Panel")
    
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.agent.reset()
            st.session_state.messages = st.session_state.messages[:1]
            st.rerun()
    with col_b:
        show_debug = st.checkbox("Show Tools", value=False)
    
    st.caption("⚡ Boards refresh from monday.com on a 2-min in-memory cache.")
    st.markdown("---")
    
    st.subheader("💡 Leadership Quick Prompts")
    quick_prompts = [
        ("⚖️ Compare Powerline vs Renewables", "Give me a leadership update comparing Powerline and Renewables."),
        ("💰 Revenue & Receivables Overview", "What is our revenue collection rate and total receivable outstanding?"),
        ("⛏️ Mining vs Construction Pipeline", "How is our sales pipeline looking for Mining vs Construction?"),
        ("🌐 Executive Sector Breakdown", "Give me an executive breakdown across all business sectors."),
        ("🛡️ Data Health & Caveats Audit", "How reliable is our data right now? Any caveats?"),
    ]
    for label, qp in quick_prompts:
        if st.button(label, key=f"btn_{label}", use_container_width=True):
            st.session_state["queued_prompt"] = qp
            st.rerun()

    st.markdown("---")
    # Export Briefing
    if len(st.session_state.messages) > 1:
        full_transcript = "# Skylark BI Agent - Executive Briefing Transcript\n\n"
        for m in st.session_state.messages:
            full_transcript += f"### {m['role'].upper()}\n{m['content']}\n\n---\n\n"
        st.download_button(
            label="📥 Export Briefing (MD)",
            data=full_transcript,
            file_name="skylark_executive_briefing.md",
            mime="text/markdown",
            use_container_width=True
        )

# Chat History Display
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# User Input
active_prompt = st.chat_input("Ask a strategic or operational business question...")
if not active_prompt and "queued_prompt" in st.session_state:
    active_prompt = st.session_state.pop("queued_prompt")

if active_prompt:
    st.session_state.messages.append({"role": "user", "content": active_prompt})
    with st.chat_message("user"):
        st.markdown(active_prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing monday.com data & reasoning..."):
            try:
                result = st.session_state.agent.ask(active_prompt)
                st.markdown(result["reply"])
                if show_debug and result.get("tool_calls"):
                    with st.expander("🛠️ ReAct Agent Tool Invocations"):
                        st.json(result["tool_calls"])
                st.session_state.messages.append({"role": "assistant", "content": result["reply"]})
            except Exception as e:
                err = f"⚠️ Query execution error: `{e}`"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})
