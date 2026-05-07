"""HC Agent -- Streamlit Web Frontend.

Adapted from GenericAgent's stapp2.py for the HC Agent architecture.
Uses agent.chat_stream() generator for streaming responses.
"""
import os, sys, html as html_mod
if sys.stdout is None: sys.stdout = open(os.devnull, "w")
if sys.stderr is None: sys.stderr = open(os.devnull, "w")
try: sys.stdout.reconfigure(errors='replace')
except: pass
try: sys.stderr.reconfigure(errors='replace')
except: pass
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
try:
    from streamlit import iframe as _st_iframe
    _embed_html = lambda h, **kw: _st_iframe(h, **{k: max(v,1) if isinstance(v,int) else v for k,v in kw.items()})
except (ImportError, AttributeError):
    from streamlit.components.v1 import html as _embed_html
import time, json, re, threading, queue
from datetime import datetime

# -- Project imports --
from config import HCConfig as Config, get_config
from hc_agent import HCAgent

# ═══════════════════════════════════════════════════
#  Anthropic Light Theme CSS (from GA stapp2.py)
# ═══════════════════════════════════════════════════
ANTHROPIC_CSS = """
<style>
:root {
    --anthropic-primary: #D4A27F;
    --anthropic-primary-hover: #C4895F;
    --anthropic-bg: #FAF9F6;
    --anthropic-bg-secondary: #EEECE2;
    --anthropic-code-bg: #F4F1EB;
    --anthropic-text: #1A1714;
    --anthropic-text-secondary: #6B6560;
    --anthropic-border: #D5CEC5;
    --anthropic-sidebar-bg: #F0EDE4;
    --anthropic-accent: #CC785C;
    --anthropic-success: #5A8A5E;
    --anthropic-warning: #C4885A;
    --anthropic-error: #C45A5A;
    --anthropic-font: 'Source Sans Pro', sans-serif;
    --anthropic-mono: 'Source Code Pro', monospace;
}
body, [data-testid="stAppViewContainer"] {
    background-color: var(--anthropic-bg) !important;
    color: var(--anthropic-text) !important;
}
.stApp { background-color: var(--anthropic-bg) !important; }
[data-testid="stHeader"], header[data-testid="stHeader"] {
    background-color: var(--anthropic-bg) !important;
    border-bottom: 1px solid var(--anthropic-border) !important;
}
[data-testid="stToolbar"] { visibility: hidden !important; }
[data-testid="stDecoration"], #MainMenu { display: none !important; visibility: hidden !important; }
[data-testid="stExpandSidebarButton"],
[data-testid="stExpandSidebarButton"] * { visibility: visible !important; }
[data-testid="stToolbar"] div:has([data-testid="stExpandSidebarButton"]) { visibility: visible !important; }
button[data-testid="stExpandSidebarButton"] {
    visibility: visible !important; background: #F4F1EA !important;
    border: none !important; color: #3B2F2A !important; border-radius: 10px !important;
}
button[data-testid="stExpandSidebarButton"]:hover {
    background: #EAE4D9 !important;
}
button[data-testid="stExpandSidebarButton"],
button[data-testid="stExpandSidebarButton"] * { color: #3B2F2A !important; fill: #3B2F2A !important; }
button[kind="header"] { visibility: hidden !important; }
[data-testid="stSidebar"], section[data-testid="stSidebar"] {
    background-color: var(--anthropic-sidebar-bg) !important;
    border-right: 1px solid var(--anthropic-border) !important;
}
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label { color: var(--anthropic-text) !important; }
[data-testid="stSidebar"] hr { border-color: var(--anthropic-border) !important; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] { width: fit-content !important; max-width: 100% !important; }
[data-testid="stSidebar"] [data-baseweb="select"] { width: fit-content !important; max-width: 100% !important; display: inline-block !important; }
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    width: fit-content !important; max-width: 100% !important;
    background: #F7F3EC !important; border: none !important; box-shadow: none !important;
    border-radius: 12px !important; min-height: 42px !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] > div:hover { background: #EFE9DE !important; border: none !important; }
[data-testid="stSidebar"] [data-baseweb="select"] input,
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] div { color: var(--anthropic-text) !important; }
[data-testid="stSidebar"] [data-baseweb="select"] span { white-space: nowrap !important; }
[data-baseweb="popover"], [data-baseweb="menu"],
[data-baseweb="popover"] > div, [data-baseweb="popover"] ul,
[data-baseweb="popover"] li, [data-baseweb="popover"] [role="option"] {
    background: #F7F3EC !important; color: var(--anthropic-text) !important;
}
[role="listbox"] {
    background: #F7F3EC !important; border: 1px solid var(--anthropic-border) !important;
    border-radius: 14px !important; box-shadow: 0 10px 30px rgba(58,47,42,0.12) !important; padding: 0.35rem !important;
}
[role="option"] { color: var(--anthropic-text) !important; background: transparent !important; border-radius: 10px !important; }
[role="option"]:hover, [role="option"][aria-selected="true"] { background: #EAE4D9 !important; }
[data-testid="stChatMessage"] {
    background: var(--anthropic-bg-secondary) !important;
    border: 1px solid var(--anthropic-border) !important;
    border-radius: 16px !important; padding: 1rem 1.25rem !important;
    color: var(--anthropic-text) !important;
    box-shadow: 0 2px 8px rgba(58,47,42,0.06) !important;
    margin-bottom: 0.75rem !important;
}
[data-testid="stChatMessage"][data-testid-type="user"] { background: #EDE7DA !important; }
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] div, [data-testid="stChatMessage"] li { color: var(--anthropic-text) !important; }
[data-testid="stChatMessage"] code {
    background: var(--anthropic-code-bg) !important; color: var(--anthropic-text) !important;
    border-radius: 6px !important; padding: 0.15em 0.4em !important;
}
[data-testid="stChatMessage"] pre {
    background: var(--anthropic-code-bg) !important;
    border: 1px solid var(--anthropic-border) !important;
    border-radius: 10px !important; padding: 1rem !important;
}
[data-testid="stChatMessage"] pre code { background: transparent !important; }
[data-testid="stChatInput"] {
    border-top: 1px solid var(--anthropic-border) !important;
    background: var(--anthropic-bg) !important;
}
[data-testid="stChatInput"] textarea {
    background: var(--anthropic-bg-secondary) !important;
    border: 1px solid var(--anthropic-border) !important;
    border-radius: 14px !important;
    color: var(--anthropic-text) !important;
}
[data-testid="stChatInput"] textarea::placeholder { color: var(--anthropic-text-secondary) !important; }
[data-testid="stChatInput"] button {
    background: var(--anthropic-primary) !important;
    color: white !important; border-radius: 10px !important; border: none !important;
}
[data-testid="stChatInput"] button:hover { background: var(--anthropic-primary-hover) !important; }
[data-testid="stChatInput"] button:disabled { background: var(--anthropic-border) !important; }
.stButton > button {
    background: var(--anthropic-primary) !important; color: white !important;
    border: none !important; border-radius: 10px !important; padding: 0.5rem 1.25rem !important;
    font-weight: 500 !important;
}
.stButton > button:hover { background: var(--anthropic-primary-hover) !important; }
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: var(--anthropic-error) !important; color: white !important;
}
.stButton > button[kind="primary"]:hover { background: #B04A4A !important; }
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3 { color: var(--anthropic-text) !important; }
.stMarkdown a { color: var(--anthropic-accent) !important; }
.stTabs [data-baseweb="tab-list"] { background: var(--anthropic-bg-secondary) !important; border-radius: 10px !important; }
.stTabs [data-baseweb="tab"] { color: var(--anthropic-text-secondary) !important; }
.stTabs [aria-selected="true"] { color: var(--anthropic-text) !important; background: var(--anthropic-bg) !important; }
.stExpander { border: 1px solid var(--anthropic-border) !important; border-radius: 12px !important; }
.stMetric { background: var(--anthropic-bg-secondary) !important; border-radius: 10px !important; padding: 1rem !important; }
.msg-timestamp { font-size: 0.72rem; color: var(--anthropic-text-secondary); margin-bottom: 0.3rem; }
.stop-btn-anchor + div { position: sticky; top: 0; z-index: 999; }
div[data-baseweb="select"] > div { min-height: 38px !important; }
::selection { background: #D4A27F40 !important; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--anthropic-border); border-radius: 3px; }
div[data-testid="stSidebarUserContent"] { padding-top: 1rem !important; }
[data-testid="stSidebar"] .stButton > button {
    background: var(--anthropic-bg) !important;
    color: var(--anthropic-text) !important;
    border: 1px solid var(--anthropic-border) !important;
    border-radius: 12px !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: var(--anthropic-bg-secondary) !important;
    border-color: var(--anthropic-primary) !important;
}
</style>
"""

# ═══════════════════════════════════════════════════
#  Agent Initialization (cached)
# ═══════════════════════════════════════════════════
@st.cache_resource
def init_agent():
    """Initialize HC Agent once, cached across reruns."""
    cfg = get_config()
    cfg.ensure_dirs()
    agent = HCAgent(cfg)
    return agent

agent = init_agent()

# ═══════════════════════════════════════════════════
#  Session State Defaults
# ═══════════════════════════════════════════════════
def init_session_state():
    defaults = {
        "messages": [],
        "streaming": False,
        "stopping": False,
        "partial_response": "",
        "reply_ts": "",
        "current_prompt": "",
        "display_queue": None,
        "deep_thinking": False,
        "deep_think_result": "",
        "autonomous_enabled": False,
        "autonomous_running": False,
        "autonomous_last_run": 0.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session_state()

# ═══════════════════════════════════════════════════
#  Apply Theme
# ═══════════════════════════════════════════════════
st.markdown(ANTHROPIC_CSS, unsafe_allow_html=True)
st.session_state.agent_name = "HC Agent"

# Welcome message
if not st.session_state.messages:
    with st.chat_message("assistant"):
        st.markdown(f'<div class="msg-timestamp">{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>', unsafe_allow_html=True)
        st.write("Welcome to HC Agent -- CSA+HCA Hybrid with CDH Memory. How can I help you?")

# ═══════════════════════════════════════════════════
#  Sidebar
# ═══════════════════════════════════════════════════
@st.fragment
def render_sidebar():
    st.markdown("### HC Agent")
    status = agent.get_status()
    st.caption(f"Turn: {status.get('turn', 0)} | Memory: {status.get('memory_count', 0)} | Skills: {status.get('skill_count', 0)}")
    st.divider()

    # ── Deep Thinking ──
    st.markdown("#### 🧠 Deep Thinking")
    dt_loop = getattr(getattr(agent, 'loop', None), 'deep_thinker', None)
    dt_currently_on = getattr(dt_loop, 'enabled', False) if dt_loop else False
    # Use session_state so toggle label changes immediately on click
    dt_key = "dt_toggle"
    if dt_key not in st.session_state:
        st.session_state[dt_key] = dt_currently_on

    def _on_dt_change():
        new_val = st.session_state[dt_key]
        if dt_loop:
            dt_loop.enabled = new_val

    st.toggle(
        "🧠 深度思考",
        key=dt_key,
        on_change=_on_dt_change,
        disabled=st.session_state.get("streaming", False),
    )

    st.divider()

    # ── Autonomous Actions ──
    st.markdown("#### 🤖 Autonomous Actions")
    auto_status = "🟢 Running" if st.session_state.autonomous_running else ("⚪ Idle" if st.session_state.autonomous_enabled else "⚫ Off")
    st.caption(f"Status: {auto_status}")

    if st.session_state.autonomous_enabled and not st.session_state.streaming:
        elapsed = time.time() - st.session_state.autonomous_last_run
        remain = max(0, 1800 - elapsed)
        mins, secs = int(remain // 60), int(remain % 60)
        st.caption(f"Next task in: {mins}m {secs}s")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ 开始空闲自主", disabled=st.session_state.autonomous_running):
            st.session_state.autonomous_enabled = True
            st.session_state.autonomous_running = True
            st.session_state.autonomous_last_run = time.time()
            st.toast("Idle autonomous mode started (30min interval)")
            st.rerun()
    with col2:
        if st.button("⏹️ 停止自主", disabled=not st.session_state.autonomous_running):
            st.session_state.autonomous_enabled = False
            st.session_state.autonomous_running = False
            st.toast("Autonomous mode stopped")
            st.rerun()

    if st.button("🚀 立即运行自主行动", disabled=st.session_state.streaming or not st.session_state.autonomous_enabled):
        st.session_state.autonomous_last_run = 0.0
        st.toast("Triggering autonomous action now...")
        st.rerun()

    st.divider()

    # ── Status & Info ──
    if st.button("Show Status"):
        st.json(status)
    if st.button("Show Memory"):
        items = agent.store.get_all() if hasattr(agent, 'store') else []
        for it in items[:20]:
            st.caption(f"[{getattr(it,'tag','')}] {getattr(it,'content','')[:60]}")
    st.divider()
    st.caption(f"Model: {getattr(agent.config.llm, 'model', 'N/A') if hasattr(agent.config, 'llm') else 'N/A'}")
    st.caption(f"Browser: {'Enabled' if getattr(agent.config.tools, 'enable_browser', False) else 'Disabled'}")

with st.sidebar:
    render_sidebar()

# ═══════════════════════════════════════════════════
#  Streaming Task Runner (threaded)
# ═══════════════════════════════════════════════════
def _stream_worker(prompt: str, q: queue.Queue, stop_event: threading.Event):
    """Worker thread: run chat_stream and push chunks to queue."""
    try:
        for chunk in agent.chat_stream(prompt):
            if stop_event.is_set():
                q.put({"done": "[Stopped by user]"})
                return
            q.put({"next": chunk})
        q.put({"done": ""})  # empty done = natural completion
    except Exception as e:
        q.put({"done": f"[Error: {e}]"})


def start_agent_task(prompt):
    q = queue.Queue()
    stop_event = threading.Event()
    t = threading.Thread(target=_stream_worker, args=(prompt, q, stop_event), daemon=True)
    t.start()
    st.session_state.display_queue = q
    st.session_state.stop_event = stop_event
    st.session_state.streaming = True
    st.session_state.stopping = False
    st.session_state.partial_response = ""
    st.session_state.reply_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.current_prompt = prompt


def poll_agent_output(max_items=30):
    q = st.session_state.display_queue
    if q is None:
        st.session_state.streaming = False
        return False
    done = False
    for _ in range(max_items):
        try:
            item = q.get_nowait()
        except queue.Empty:
            break
        if "next" in item:
            st.session_state.partial_response += item["next"]
        if "done" in item:
            done_text = item["done"]
            if done_text:
                st.session_state.partial_response += done_text
            done = True
            break
    if done:
        st.session_state.streaming = False
        st.session_state.stopping = False
        st.session_state.display_queue = None
    return done


def _get_response_segments(text):
    """Split response into segments by turn markers."""
    return [p for p in re.split(r'(?=\*\*LLM Running \(Turn \d+\) \.\.\.\*\*)', text) if p.strip()] or [text]


# ═══════════════════════════════════════════════════
#  Autonomous Action Execution (30-min interval)
# ═══════════════════════════════════════════════════
if (st.session_state.get("autonomous_enabled")
    and not st.session_state.get("streaming")):
    elapsed = time.time() - st.session_state.get("autonomous_last_run", 0)
    if elapsed >= 1800:  # 30 minutes
        st.session_state.autonomous_last_run = time.time()
        st.session_state.autonomous_running = True
        # Build SOP-compliant autonomous task prompt
        auto_prompt = (
            "[SYSTEM: Autonomous Self-Improvement Cycle]\n"
            "You are in idle autonomous mode. Follow the autonomous_operation_sop strictly:\n"
            "1. Check TODO file for next unmarked item [ ]\n"
            "2. Pick ONE task, execute it (read-only probes OK; writes only in cwd)\n"
            "3. Write report to ./autonomous_reports/ using autonomous_helper.complete_task()\n"
            "4. Update TODO: mark completed item as [x]\n"
            "5. Summarize findings briefly\n\n"
            "Proceed now. Do NOT ask for confirmation."
        )
        start_agent_task(auto_prompt)
        st.toast("🤖 Autonomous task triggered (30-min cycle)")
        st.rerun()

# Auto-clear running flag when streaming finishes
if st.session_state.get("autonomous_running") and not st.session_state.get("streaming"):
    st.session_state.autonomous_running = False


def render_message(role, content, ts="", unsafe_allow_html=True):
    with st.chat_message(role):
        if ts:
            st.markdown(f'<div class="msg-timestamp">{ts}</div>', unsafe_allow_html=True)
        st.markdown(content, unsafe_allow_html=unsafe_allow_html)


def finish_streaming_message():
    reply_ts = st.session_state.reply_ts
    for seg in _get_response_segments(st.session_state.partial_response):
        st.session_state.messages.append({"role": "assistant", "content": seg, "time": reply_ts})
    st.session_state.last_reply_time = int(time.time())
    st.session_state.partial_response = st.session_state.reply_ts = st.session_state.current_prompt = ""


def render_streaming_area():
    if not st.session_state.streaming:
        return
    with st.container():
        st.markdown('<span class="stop-btn-anchor"></span>', unsafe_allow_html=True)
        if st.button("Stop Generation", type="primary"):
            st.session_state.stop_event.set()
            st.session_state.stopping = True
            st.toast("Stop signal sent")
            st.rerun()
    reply_ts = st.session_state.reply_ts
    with st.empty().container():
        segments = _get_response_segments(st.session_state.partial_response)
        for i, seg in enumerate(segments):
            cursor = "" if i < len(segments) - 1 else " |"
            render_message("assistant", seg + cursor, ts=reply_ts, unsafe_allow_html=False)
    if poll_agent_output():
        finish_streaming_message()
    else:
        time.sleep(0.15)
    st.rerun()


# ═══════════════════════════════════════════════════
#  Main Render Loop
# ═══════════════════════════════════════════════════
for msg in st.session_state.messages:
    render_message(msg["role"], msg["content"], ts=msg.get("time", ""), unsafe_allow_html=True)

if st.session_state.streaming:
    render_streaming_area()

if prompt := st.chat_input("Enter your instruction", disabled=st.session_state.streaming):
    st.session_state.messages.append({
        "role": "user",
        "content": prompt,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    start_agent_task(prompt)
    st.rerun()
