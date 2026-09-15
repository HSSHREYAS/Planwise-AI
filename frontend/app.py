"""
PlanWise AI - Streamlit Frontend

Modern, responsive UI with dark theme for the planning assistant.
All business logic is in the backend — this is a thin UI layer.
"""

import streamlit as st
from services.api_client import api_client


# ── Page Config ─────────────────────────────────────────────────

st.set_page_config(
    page_title="PlanWise AI",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Custom CSS ──────────────────────────────────────────────────

st.markdown("""
<style>
/* ── Import Google Font ──────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Root Theme Variables ────────────────────────────────── */
:root {
    --bg-primary: #0f0f1a;
    --bg-secondary: #1a1a2e;
    --bg-card: rgba(30, 30, 50, 0.7);
    --bg-glass: rgba(255, 255, 255, 0.04);
    --border-glass: rgba(255, 255, 255, 0.08);
    --text-primary: #e8e8f0;
    --text-secondary: #9d9db8;
    --text-muted: #6b6b8a;
    --accent-primary: #7c3aed;
    --accent-secondary: #a78bfa;
    --accent-glow: rgba(124, 58, 237, 0.3);
    --success: #34d399;
    --warning: #fbbf24;
    --error: #f87171;
    --gradient-1: linear-gradient(135deg, #7c3aed 0%, #2563eb 100%);
    --gradient-2: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    --shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.3);
    --radius: 12px;
    --radius-sm: 8px;
    --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* ── Global Styles ───────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

[data-testid="stAppViewContainer"] {
    background: var(--gradient-2) !important;
}

.main .block-container {
    max-width: 900px !important;
    padding: 1.5rem 1.5rem 6rem 1.5rem !important;
}

/* ── Scrollbar ───────────────────────────────────────────── */
::-webkit-scrollbar {
    width: 6px;
}
::-webkit-scrollbar-track {
    background: var(--bg-primary);
}
::-webkit-scrollbar-thumb {
    background: var(--text-muted);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: var(--text-secondary);
}

/* ── Sidebar ─────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border-glass) !important;
}

[data-testid="stSidebar"] [data-testid="stMarkdown"] {
    color: var(--text-primary) !important;
}

[data-testid="stSidebar"] .stButton > button {
    background: var(--gradient-1) !important;
    color: white !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    padding: 0.6rem 1rem !important;
    transition: var(--transition) !important;
    box-shadow: 0 4px 15px var(--accent-glow) !important;
}

[data-testid="stSidebar"] .stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px var(--accent-glow) !important;
}

/* ── Status Badges ───────────────────────────────────────── */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 500;
    letter-spacing: 0.02em;
    margin-bottom: 4px;
}

.status-connected {
    background: rgba(52, 211, 153, 0.12);
    color: var(--success);
    border: 1px solid rgba(52, 211, 153, 0.2);
}

.status-warning {
    background: rgba(251, 191, 36, 0.12);
    color: var(--warning);
    border: 1px solid rgba(251, 191, 36, 0.2);
}

.status-error {
    background: rgba(248, 113, 113, 0.12);
    color: var(--error);
    border: 1px solid rgba(248, 113, 113, 0.2);
}

/* ── Chat Messages ───────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: var(--bg-glass) !important;
    border: 1px solid var(--border-glass) !important;
    border-radius: var(--radius) !important;
    padding: 1rem 1.25rem !important;
    margin-bottom: 0.75rem !important;
    backdrop-filter: blur(10px) !important;
    transition: var(--transition) !important;
}

[data-testid="stChatMessage"]:hover {
    border-color: rgba(255, 255, 255, 0.12) !important;
    background: rgba(255, 255, 255, 0.06) !important;
}

/* User message accent */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    border-left: 3px solid var(--accent-primary) !important;
}

/* Assistant message accent */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    border-left: 3px solid var(--accent-secondary) !important;
}

/* ── Chat Input ──────────────────────────────────────────── */
[data-testid="stChatInput"] {
    border-color: var(--border-glass) !important;
}

[data-testid="stChatInput"] textarea {
    background: var(--bg-card) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border-glass) !important;
    border-radius: var(--radius) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.9rem !important;
    caret-color: var(--accent-primary) !important;
}

[data-testid="stChatInput"] textarea:focus {
    border-color: var(--accent-primary) !important;
    box-shadow: 0 0 0 2px var(--accent-glow) !important;
}

[data-testid="stChatInput"] button {
    background: var(--gradient-1) !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
}

/* ── Expander ────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: var(--bg-glass) !important;
    border: 1px solid var(--border-glass) !important;
    border-radius: var(--radius) !important;
    margin-top: 0.5rem !important;
}

[data-testid="stExpander"] summary {
    color: var(--accent-secondary) !important;
    font-weight: 500 !important;
}

/* ── Metric ──────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--bg-glass) !important;
    border: 1px solid var(--border-glass) !important;
    border-radius: var(--radius) !important;
    padding: 1rem !important;
}

[data-testid="stMetric"] label {
    color: var(--text-secondary) !important;
}

[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: var(--accent-secondary) !important;
}

/* ── Dividers ────────────────────────────────────────────── */
hr {
    border-color: var(--border-glass) !important;
    margin: 0.75rem 0 !important;
}

/* ── Alerts ──────────────────────────────────────────────── */
.stAlert {
    border-radius: var(--radius-sm) !important;
    font-size: 0.85rem !important;
}

/* ── Header/Branding ─────────────────────────────────────── */
.brand-header {
    text-align: center;
    padding: 1rem 0 0.5rem 0;
}

.brand-header h1 {
    font-size: 1.6rem;
    font-weight: 700;
    background: var(--gradient-1);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 2px;
}

.brand-header p {
    color: var(--text-muted);
    font-size: 0.78rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

/* ── Plan Card ───────────────────────────────────────────── */
.plan-card {
    background: var(--bg-glass);
    border: 1px solid var(--border-glass);
    border-radius: var(--radius);
    padding: 1rem 1.25rem;
    margin: 0.5rem 0;
    backdrop-filter: blur(8px);
}

.plan-card h4 {
    color: var(--accent-secondary);
    margin: 0 0 0.5rem 0;
    font-weight: 600;
}

.plan-card .detail {
    color: var(--text-secondary);
    font-size: 0.85rem;
    line-height: 1.6;
}

/* ── Welcome Empty State ─────────────────────────────────── */
.welcome-container {
    text-align: center;
    padding: 3rem 1rem;
    color: var(--text-muted);
}

.welcome-container .emoji {
    font-size: 3rem;
    margin-bottom: 1rem;
    display: block;
}

.welcome-container h2 {
    color: var(--text-primary);
    font-weight: 600;
    font-size: 1.4rem;
    margin-bottom: 0.5rem;
}

.welcome-container p {
    max-width: 480px;
    margin: 0 auto;
    line-height: 1.6;
    font-size: 0.9rem;
}

.suggestion-chips {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin-top: 1.5rem;
}

.suggestion-chip {
    background: var(--bg-glass);
    border: 1px solid var(--border-glass);
    border-radius: 20px;
    padding: 8px 16px;
    font-size: 0.8rem;
    color: var(--text-secondary);
    transition: var(--transition);
    cursor: default;
}

.suggestion-chip:hover {
    border-color: var(--accent-primary);
    color: var(--accent-secondary);
    background: rgba(124, 58, 237, 0.08);
}

/* ── Spinner Override ────────────────────────────────────── */
.stSpinner > div {
    border-top-color: var(--accent-primary) !important;
}

/* ── Session Info ────────────────────────────────────────── */
.session-info {
    font-size: 0.72rem;
    color: var(--text-muted);
    font-family: 'Inter', monospace;
    opacity: 0.8;
}

/* ── Footer ──────────────────────────────────────────────── */
.footer-text {
    text-align: center;
    color: var(--text-muted);
    font-size: 0.7rem;
    padding: 0.5rem 0;
    opacity: 0.7;
    letter-spacing: 0.03em;
}

/* ── Responsive ──────────────────────────────────────────── */
@media (max-width: 768px) {
    .main .block-container {
        padding: 1rem 0.75rem 5rem 0.75rem !important;
    }
    
    [data-testid="stChatMessage"] {
        padding: 0.75rem 1rem !important;
    }
    
    .welcome-container {
        padding: 2rem 0.5rem;
    }
    
    .welcome-container h2 {
        font-size: 1.2rem;
    }
    
    .suggestion-chips {
        gap: 6px;
    }
    
    .suggestion-chip {
        font-size: 0.75rem;
        padding: 6px 12px;
    }
    
    .brand-header h1 {
        font-size: 1.3rem;
    }
}

@media (max-width: 480px) {
    .main .block-container {
        padding: 0.5rem 0.5rem 5rem 0.5rem !important;
        max-width: 100% !important;
    }
    
    [data-testid="stSidebar"] {
        min-width: 220px !important;
        max-width: 260px !important;
    }
    
    .suggestion-chips {
        flex-direction: column;
        align-items: center;
    }
}

/* ── Hide Streamlit Defaults ─────────────────────────────── */
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ── Session State Init ──────────────────────────────────────────

def init_session():
    """Initialize Streamlit session state."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "current_plan" not in st.session_state:
        st.session_state.current_plan = None
    if "validation" not in st.session_state:
        st.session_state.validation = None
    if "backend_status" not in st.session_state:
        st.session_state.backend_status = None


def ensure_session():
    """Ensure we have an active backend session."""
    if st.session_state.session_id is None:
        session_id = api_client.create_session()
        if session_id:
            st.session_state.session_id = session_id
        else:
            st.error("⚠️ Could not connect to the backend. Please ensure the server is running on port 8000.")
            st.stop()


init_session()


# ── Sidebar ─────────────────────────────────────────────────────

with st.sidebar:
    # Brand header
    st.markdown("""
    <div class="brand-header">
        <h1>🗺️ PlanWise AI</h1>
        <p>Intelligent Planning Assistant</p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # Backend status check
    health = api_client.health_check()
    if health.get("status") == "ok":
        st.markdown(
            '<div class="status-badge status-connected">● Backend Connected</div>',
            unsafe_allow_html=True,
        )
        if health.get("ollama_available"):
            st.markdown(
                '<div class="status-badge status-connected">● AI Model Ready</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="status-badge status-warning">● AI Model Loading</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="status-badge status-error">● Backend Offline</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # New session button
    if st.button("✨ New Session", use_container_width=True, key="new_session"):
        st.session_state.session_id = None
        st.session_state.messages = []
        st.session_state.current_plan = None
        st.session_state.validation = None
        st.rerun()

    # Session info
    if st.session_state.session_id:
        st.markdown(
            f'<div class="session-info">Session: {st.session_state.session_id[:8]}…</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # Current plan info
    if st.session_state.current_plan:
        plan = st.session_state.current_plan
        st.markdown("##### 📋 Current Plan")

        plan_html_parts = []
        if plan.get("location"):
            plan_html_parts.append(f'<div class="detail">📍 {plan["location"]}</div>')
        if plan.get("duration_days"):
            plan_html_parts.append(f'<div class="detail">📅 {plan["duration_days"]} day(s)</div>')
        if plan.get("estimated_total_cost") is not None:
            plan_html_parts.append(
                f'<div class="detail">💰 Est. ₹{plan["estimated_total_cost"]:.0f}</div>'
            )

        if plan_html_parts:
            st.markdown(
                f'<div class="plan-card">{"".join(plan_html_parts)}</div>',
                unsafe_allow_html=True,
            )

    # Validation status
    if st.session_state.validation:
        val = st.session_state.validation
        if val.get("valid"):
            st.markdown(
                '<div class="status-badge status-connected">✓ Constraints OK</div>',
                unsafe_allow_html=True,
            )
        else:
            for v in val.get("violations", []):
                st.error(f"❌ {v}")
        for w in val.get("warnings", []):
            st.warning(f"⚠️ {w}")

    st.divider()
    st.markdown(
        '<div class="footer-text">Qwen2.5-3B · Ollama · FAISS · MultiWOZ 2.2</div>',
        unsafe_allow_html=True,
    )


# ── Main Content ────────────────────────────────────────────────

# Ensure session exists
ensure_session()

# Welcome state (no messages yet)
if not st.session_state.messages:
    st.markdown("""
    <div class="welcome-container">
        <span class="emoji">🗺️</span>
        <h2>What would you like to plan?</h2>
        <p>I can help you find hotels, restaurants, attractions, plan trips, or create study schedules — all powered by real data.</p>
        <div class="suggestion-chips">
            <span class="suggestion-chip">🏨 Find hotels in the centre</span>
            <span class="suggestion-chip">🍽️ Cheap restaurants in the south</span>
            <span class="suggestion-chip">🎯 Attractions to visit</span>
            <span class="suggestion-chip">📅 Plan a 2-day Cambridge trip</span>
            <span class="suggestion-chip">📚 Create a study schedule</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Display conversation
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("What would you like to plan?"):
    # Display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Send to backend
    with st.chat_message("assistant"):
        with st.spinner("🔍 Searching & planning..."):
            response = api_client.send_message(
                st.session_state.session_id, prompt
            )

    status = response.get("status", "error")
    message = response.get("message", "Something went wrong.")

    # Display response
    st.markdown(message)
    st.session_state.messages.append({"role": "assistant", "content": message})

    # Update plan display
    plan_data = response.get("plan")
    if plan_data:
        st.session_state.current_plan = plan_data

    # Update validation display
    validation_data = response.get("validation")
    if validation_data:
        st.session_state.validation = validation_data

    # Show plan details if available
    if plan_data and plan_data.get("days"):
        with st.expander("📋 View Detailed Plan", expanded=False):
            for day in plan_data["days"]:
                st.markdown(f"### Day {day['day']}")
                for slot in day.get("slots", []):
                    st.markdown(f"**{slot['time_of_day'].capitalize()}**")
                    activities = slot.get("activities", [])
                    if activities:
                        for act in activities:
                            cost_str = ""
                            if act.get("estimated_cost"):
                                cost_str = f" — ₹{act['estimated_cost']:.0f}"
                            act_type = act.get("type", "").capitalize()
                            st.markdown(
                                f"- **{act['name']}** `{act_type}`{cost_str}"
                            )
                    else:
                        st.markdown("- _Free time_")
                st.divider()

            # Budget summary
            if plan_data.get("estimated_total_cost") is not None:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        "Estimated Total",
                        f"₹{plan_data['estimated_total_cost']:.0f}",
                    )

            # Assumptions
            assumptions = plan_data.get("assumptions", [])
            if assumptions:
                st.caption("📝 " + " · ".join(assumptions))

    # Show validation info
    if validation_data:
        if not validation_data.get("valid"):
            for v in validation_data.get("violations", []):
                st.error(f"❌ {v}")
        for w in validation_data.get("warnings", []):
            st.info(f"ℹ️ {w}")

    st.rerun()
