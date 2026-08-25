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
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    /* Main Header */
    .main-header {
        background: linear-gradient(135deg, #1E1B4B 0%, #312E81 50%, #4338CA 100%);
        padding: 26px 30px;
        border-radius: 18px;
        color: #FFFFFF;
        margin-bottom: 22px;
        box-shadow: 0 10px 25px -5px rgba(49, 46, 129, 0.2), 0 4px 6px -2px rgba(49, 46, 129, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.15);
    }
    
    .main-header h1 {
        color: #FFFFFF !important;
        font-weight: 800;
        font-size: 1.95rem;
        margin: 0 0 6px 0;
        display: flex;
        align-items: center;
        gap: 12px;
        letter-spacing: -0.5px;
    }
    
    .main-header p {
        color: #E0E7FF !important;
        font-size: 0.95rem;
        margin: 0;
        line-height: 1.5;
    }
    
    .status-badge {
        display: inline-flex;
        align-items: center;
        background: rgba(16, 185, 129, 0.2);
        border: 1px solid rgba(16, 185, 129, 0.5);
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
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.03);
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        border-color: #6366F1;
        box-shadow: 0 6px 16px rgba(99, 102, 241, 0.12);
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
    
    /* User Message Styling: Shift to Right with Dynamic Bubble Width */
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
    [data-testid="stChatMessage"]:has([aria-label*="user" i]),
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        flex-direction: row-reverse !important;
        background: linear-gradient(135deg, #4338CA 0%, #3730A3 100%) !important;
        border: 1px solid #4F46E5 !important;
        color: #FFFFFF !important;
        border-radius: 18px 18px 4px 18px !important;
        margin-left: auto !important;
        margin-right: 0 !important;
        width: fit-content !important;
        max-width: 80% !important;
        padding: 12px 18px !important;
        box-shadow: 0 4px 12px rgba(67, 56, 202, 0.2) !important;
    }
    
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
    [data-testid="stChatMessage"]:has([aria-label*="user" i]) p {
        color: #FFFFFF !important;
    }

    /* Assistant Message Styling: Left aligned with Dynamic Bubble Width */
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]),
    [data-testid="stChatMessage"]:has([aria-label*="assistant" i]),
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        flex-direction: row !important;
        background: #FFFFFF !important;
        border: 1px solid #E2E8F0 !important;
        border-left: 4px solid #4F46E5 !important;
        border-radius: 18px 18px 18px 4px !important;
        margin-right: auto !important;
        margin-left: 0 !important;
        width: fit-content !important;
        max-width: 92% !important;
        padding: 14px 20px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04) !important;
    }
    
    [data-testid="stChatMessageContent"] {
        width: fit-content !important;
    }
    
    /* Sidebar Polish */
    section[data-testid="stSidebar"] {
        background-color: #F8FAFC;
        border-right: 1px solid #E2E8F0;
    }
    
    /* Left-Aligned Quick Prompt Buttons */
    div[data-testid="stSidebar"] .stButton > button {
        border-radius: 10px;
        font-weight: 600;
        background: #FFFFFF;
        color: #1E293B;
        border: 1px solid #E2E8F0;
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 10px 14px !important;
        font-size: 0.84rem !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
        transition: all 0.2s ease;
        margin-bottom: 2px;
    }
    div[data-testid="stSidebar"] .stButton > button:hover {
        border-color: #4F46E5;
        color: #4F46E5;
        background: #EEF2FF;
        box-shadow: 0 2px 6px rgba(79, 70, 229, 0.12);
        transform: translateX(2px);
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
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
        <div style="background: linear-gradient(135deg, #4F46E5 0%, #3730A3 100%); width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 22px; box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);">
            🦅
        </div>
        <div>
            <div style="font-weight: 800; font-size: 1.1rem; color: #0F172A; letter-spacing: -0.3px;">Skylark BI Agent</div>
            <div style="font-size: 0.72rem; color: #64748B; text-transform: uppercase; letter-spacing: 0.6px; font-weight: 700;">Executive Suite</div>
        </div>
    </div>
    
    <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 12px 14px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
        <div style="font-size: 0.7rem; color: #64748B; text-transform: uppercase; font-weight: 700; letter-spacing: 0.6px; margin-bottom: 8px;">System Telemetry</div>
        <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 5px;">
            <span style="color: #475569;">monday.com API:</span>
            <span style="color: #059669; font-weight: 700;">● Active (v2)</span>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 5px;">
            <span style="color: #475569;">AI Model:</span>
            <span style="color: #4F46E5; font-weight: 700;">Llama 3.3 70B</span>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 0.8rem;">
            <span style="color: #475569;">Cache Policy:</span>
            <span style="color: #D97706; font-weight: 700;">2-Min TTL</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.agent.reset()
            st.session_state.messages = st.session_state.messages[:1]
            st.rerun()
    with col_b:
        show_debug = st.checkbox("Show Tools", value=False)
    
    st.markdown("---")
    
    st.subheader("💡 Leadership Quick Prompts")
    st.caption("Click any query to execute an instant executive briefing:")
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
    avatar = "👤" if msg["role"] == "user" else "🦅"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if show_debug and msg.get("tool_calls"):
            with st.expander(f"🛠️ ReAct Agent Tool Invocations ({len(msg['tool_calls'])} calls)", expanded=True):
                for i, tc in enumerate(msg["tool_calls"], 1):
                    st.markdown(f"**Step {i}: `{tc.get('tool')}`**")
                    st.caption(f"Input parameters: `{tc.get('input')}`")
                    st.json(tc.get("result"))

# User Input
active_prompt = st.chat_input("Ask a strategic or operational business question...")
if not active_prompt and "queued_prompt" in st.session_state:
    active_prompt = st.session_state.pop("queued_prompt")

if active_prompt:
    st.session_state.messages.append({"role": "user", "content": active_prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(active_prompt)

    with st.chat_message("assistant", avatar="🦅"):
        with st.spinner("Analyzing monday.com data & reasoning..."):
            try:
                result = st.session_state.agent.ask(active_prompt)
                st.markdown(result["reply"])
                tool_calls = result.get("tool_calls", [])
                if show_debug and tool_calls:
                    with st.expander(f"🛠️ ReAct Agent Tool Invocations ({len(tool_calls)} calls)", expanded=True):
                        for i, tc in enumerate(tool_calls, 1):
                            st.markdown(f"**Step {i}: `{tc.get('tool')}`**")
                            st.caption(f"Input parameters: `{tc.get('input')}`")
                            st.json(tc.get("result"))
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result["reply"],
                    "tool_calls": tool_calls
                })
            except Exception as e:
                err = f"⚠️ Query execution error: `{e}`"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err, "tool_calls": []})
