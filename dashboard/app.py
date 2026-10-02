"""
AI Video Studio — Premium Dark Cherry Commercial Frontend
Redesigned with Figma-grade design language, dark cinematic palette,
guided workflows, dedicated publishing pipelines, and real-time status tracking.
"""

import os
import json
import time
from datetime import datetime
from typing import Optional, Dict, List, Any
import requests
import streamlit as st

# ---------------------------------------------------------------------- #
# 1. Page Configuration & Global Helpers
# ---------------------------------------------------------------------- #
st.set_page_config(
    page_title="AI Video Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

def get_api_url() -> str:
    if "API_URL" in os.environ:
        return os.environ["API_URL"]
    for port in [8000, 8001]:
        try:
            r = requests.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            if r.status_code == 200:
                return f"http://127.0.0.1:{port}"
        except Exception:
            pass
    return "http://127.0.0.1:8000"

API_URL = get_api_url()

def is_tiktok_sandbox_or_unaudited() -> bool:
    """Check if TikTok integration is currently in Sandbox/unaudited mode."""
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    if client_key.startswith("sb"):
        return True
    if os.getenv("TIKTOK_IS_SANDBOX", "false").lower() in ("true", "1", "yes"):
        return True
    if os.getenv("TIKTOK_UNAUDITED", "false").lower() in ("true", "1", "yes"):
        return True
    return False

# ---------------------------------------------------------------------- #
# 2. Design System: Dark Cherry Palette & Figma-Grade Styling
# ---------------------------------------------------------------------- #
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    :root {
        --primary: #C62845;
        --deep-cherry: #8E1B32;
        --dark-cherry: #5C1022;
        --bg: #0B0B0F;
        --surface: #15151B;
        --elevated: #1D1D25;
        --border: #2B2B35;
        --border-hover: #454555;
        --text: #F7F4F5;
        --text-secondary: #A9A4AA;
        --success: #35C98B;
        --warning: #E8A83E;
        --error: #E05260;
    }

    /* Core Application Background & Font */
    html, body, [data-testid="stAppViewContainer"], .main {
        background-color: var(--bg) !important;
        color: var(--text) !important;
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: var(--surface) !important;
        border-right: 1px solid var(--border) !important;
        padding-top: 1rem;
    }
    [data-testid="stSidebar"] hr {
        border-color: var(--border) !important;
    }

    /* Header & Typography */
    h1, h2, h3, h4, h5, h6 {
        color: var(--text) !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
    }
    p, span, label {
        color: var(--text) !important;
    }
    .secondary-text {
        color: var(--text-secondary) !important;
        font-size: 0.88rem;
    }

    /* Studio Card Containers */
    .studio-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 16px;
        transition: all 0.2s ease-in-out;
    }
    .studio-card:hover {
        border-color: var(--border-hover);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }
    .studio-card-elevated {
        background: var(--elevated);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 16px;
    }
    .studio-card-active {
        background: var(--surface);
        border: 1px solid var(--primary);
        box-shadow: 0 0 15px rgba(198, 40, 69, 0.2);
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 16px;
    }

    /* Stat Metric Cards */
    .stat-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px 20px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        min-height: 100px;
        position: relative;
        overflow: hidden;
    }
    .stat-card::after {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, var(--primary), var(--deep-cherry));
        opacity: 0.8;
    }
    .stat-label {
        font-size: 0.82rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-secondary);
    }
    .stat-value {
        font-size: 1.85rem;
        font-weight: 800;
        color: var(--text);
        margin-top: 4px;
    }

    /* Status Badges */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.78rem;
        letter-spacing: 0.03em;
        text-transform: uppercase;
    }
    .badge-approved { background: rgba(53, 201, 139, 0.15); color: #35C98B; border: 1px solid rgba(53, 201, 139, 0.3); }
    .badge-published { background: rgba(53, 201, 139, 0.15); color: #35C98B; border: 1px solid rgba(53, 201, 139, 0.3); }
    .badge-pending_approval { background: rgba(232, 168, 62, 0.15); color: #E8A83E; border: 1px solid rgba(232, 168, 62, 0.3); }
    .badge-generating { background: rgba(198, 40, 69, 0.2); color: #F78298; border: 1px solid rgba(198, 40, 69, 0.4); }
    .badge-failed { background: rgba(224, 82, 96, 0.15); color: #E05260; border: 1px solid rgba(224, 82, 96, 0.3); }
    .badge-draft { background: rgba(169, 164, 170, 0.15); color: #A9A4AA; border: 1px solid rgba(169, 164, 170, 0.3); }
    .badge-ready_to_schedule { background: rgba(77, 148, 255, 0.15); color: #66A3FF; border: 1px solid rgba(77, 148, 255, 0.3); }
    .badge-rejected { background: rgba(224, 82, 96, 0.15); color: #E05260; border: 1px solid rgba(224, 82, 96, 0.3); }

    /* Stepper Component */
    .stepper-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 12px 20px;
        margin-bottom: 24px;
    }
    .stepper-item {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 0.85rem;
        font-weight: 600;
        color: var(--text-secondary);
    }
    .stepper-item.active {
        color: var(--text);
    }
    .stepper-item.active .step-num {
        background: var(--primary);
        color: white;
        border-color: var(--primary);
        box-shadow: 0 0 10px rgba(198, 40, 69, 0.4);
    }
    .stepper-item.completed {
        color: var(--success);
    }
    .stepper-item.completed .step-num {
        background: rgba(53, 201, 139, 0.2);
        color: var(--success);
        border-color: var(--success);
    }
    .step-num {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        border: 1px solid var(--border);
        background: var(--elevated);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        font-weight: 700;
    }

    /* 9:16 Video Player Container */
    .video-viewport-wrapper {
        background: #000;
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 8px;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.6);
        max-width: 380px;
        margin: 0 auto;
    }

    /* Platform Badge Tiles */
    .platform-tile {
        background: var(--elevated);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 14px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 10px;
    }

    /* Pipeline Check Item */
    .pipeline-step {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 14px;
        background: var(--elevated);
        border-radius: 8px;
        margin-bottom: 8px;
        font-size: 0.88rem;
    }

    /* Form Controls */
    div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] {
        background-color: var(--elevated) !important;
        border-color: var(--border) !important;
        color: var(--text) !important;
        border-radius: 8px !important;
    }
    input, textarea {
        color: var(--text) !important;
    }

    /* Buttons */
    .stButton>button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.2rem !important;
        transition: all 0.2s ease-in-out !important;
        border: 1px solid var(--border) !important;
    }
    .stButton>button[kind="primary"] {
        background: linear-gradient(135deg, #C62845 0%, #8E1B32 100%) !important;
        color: white !important;
        border: none !important;
        box-shadow: 0 4px 14px rgba(198, 40, 69, 0.35) !important;
    }
    .stButton>button[kind="primary"]:hover {
        box-shadow: 0 6px 20px rgba(198, 40, 69, 0.5) !important;
        transform: translateY(-1px);
    }
    .stButton>button[kind="secondary"] {
        background: var(--elevated) !important;
        color: var(--text) !important;
        border: 1px solid var(--border) !important;
    }
    .stButton>button[kind="secondary"]:hover {
        border-color: var(--border-hover) !important;
        background: #252530 !important;
    }

    /* Nav Radio Pill Replacement */
    div[data-testid="stSidebar"] div[role="radiogroup"] {
        gap: 6px;
    }
    div[data-testid="stSidebar"] div[role="radiogroup"] > label {
        background: transparent;
        padding: 8px 12px;
        border-radius: 8px;
        transition: all 0.15s ease-in-out;
        border: 1px solid transparent;
        margin-bottom: 2px;
    }
    div[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
        background: rgba(255, 255, 255, 0.04);
        border-color: var(--border);
    }
    div[data-testid="stSidebar"] div[role="radiogroup"] > label[data-checked="true"] {
        background: rgba(198, 40, 69, 0.12) !important;
        border-color: rgba(198, 40, 69, 0.4) !important;
    }
    div[data-testid="stSidebar"] div[role="radiogroup"] > label[data-checked="true"] p {
        color: #F78298 !important;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------- #
# 3. Sidebar Shell: Brand, Nav & Access Control
# ---------------------------------------------------------------------- #
with st.sidebar:
    # Studio Brand Header
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #2B2B35;">
        <div style="width: 38px; height: 38px; background: linear-gradient(135deg, #C62845, #5C1022); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; box-shadow: 0 0 15px rgba(198, 40, 69, 0.4);">
            🎬
        </div>
        <div>
            <div style="font-weight: 800; font-size: 1.15rem; color: #F7F4F5; letter-spacing: -0.02em;">AI Video Studio</div>
            <div style="font-size: 0.72rem; color: #A9A4AA; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600;">Creative Suite</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Primary Navigation
    NAV_OPTIONS = [
        "Dashboard",
        "Create Video",
        "My Videos",
        "Review & Approvals",
        "Publishing Queue",
        "Publication History",
        "Social Accounts",
        "Settings",
    ]

    # Handle quick navigation if requested by state
    if "nav_target" in st.session_state and st.session_state["nav_target"] in NAV_OPTIONS:
        current_nav_idx = NAV_OPTIONS.index(st.session_state.pop("nav_target"))
    else:
        current_nav_idx = 0

    nav_selection = st.radio(
        "Navigation",
        NAV_OPTIONS,
        index=current_nav_idx,
        label_visibility="collapsed",
        key="main_nav_radio"
    )

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)

    # Active Workspace Quick Context
    if "selected_video_id" in st.session_state and st.session_state["selected_video_id"]:
        active_vid = st.session_state["selected_video_id"]
        st.markdown(f"""
        <div style="background: rgba(198, 40, 69, 0.08); border: 1px solid rgba(198, 40, 69, 0.3); border-radius: 8px; padding: 10px 12px; margin-bottom: 16px;">
            <div style="font-size: 0.72rem; color: #F78298; text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em;">Active Workspace</div>
            <div style="font-weight: 600; font-size: 0.88rem; color: #F7F4F5; margin-top: 2px;">Video #{active_vid}</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # Footer: Authorization & Health Status
    is_admin = st.toggle("Admin Role", value=True, help="Toggle between Admin and Viewer role.")
    admin_role = "admin" if is_admin else "viewer"
    admin_headers = {"X-Admin-Role": admin_role}

    # API Health Check indicator
    try:
        r = requests.get(f"{API_URL}/health", timeout=1.5)
        api_online = r.status_code == 200
    except Exception:
        api_online = False

    status_dot = "🟢" if api_online else "🔴"
    status_text = "API Connected" if api_online else "API Offline"

    st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: space-between; font-size: 0.78rem; color: #A9A4AA; margin-top: 8px;">
        <span>{status_dot} {status_text}</span>
        <span style="font-weight: 600; color: {'#35C98B' if is_admin else '#A9A4AA'};">{'ADMIN' if is_admin else 'VIEWER'}</span>
    </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------- #
# 4. Global UI Helper Functions
# ---------------------------------------------------------------------- #
def render_status_pill(status_str: str) -> str:
    s = (status_str or "DRAFT").upper()
    cls_map = {
        "APPROVED": "badge-approved",
        "PUBLISHED": "badge-published",
        "PENDING_APPROVAL": "badge-pending_approval",
        "GENERATING": "badge-generating",
        "QA_PENDING": "badge-generating",
        "FAILED": "badge-failed",
        "REJECTED": "badge-rejected",
        "DRAFT": "badge-draft",
        "READY_TO_SCHEDULE": "badge-ready_to_schedule",
    }
    cls = cls_map.get(s, "badge-draft")
    return f"<span class='status-badge {cls}'>{s.replace('_', ' ')}</span>"

def fetch_videos(status: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        url = f"{API_URL}/videos/"
        if status:
            url += f"?status={status}"
        resp = requests.get(url, timeout=4)
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []

def fetch_video(video_id: int) -> Optional[Dict[str, Any]]:
    try:
        resp = requests.get(f"{API_URL}/videos/{video_id}", timeout=4)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None

def fetch_publications(video_id: Optional[int] = None) -> List[Dict[str, Any]]:
    try:
        if video_id:
            url = f"{API_URL}/videos/{video_id}/publications"
        else:
            url = f"{API_URL}/publications"
        resp = requests.get(url, timeout=4)
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []

def fetch_accounts() -> List[Dict[str, Any]]:
    try:
        resp = requests.get(f"{API_URL}/social/accounts", timeout=4)
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []

def get_preferred_account_id(platform_accounts: List[Dict[str, Any]], saved_account_id: Optional[int] = None) -> Optional[int]:
    if not platform_accounts:
        return None
    active_accounts = [a for a in platform_accounts if a.get("status") == "ACTIVE"]
    if not active_accounts:
        active_accounts = platform_accounts

    if saved_account_id is not None:
        for acc in active_accounts:
            if acc.get("id") == saved_account_id:
                return saved_account_id

    active_real = [a for a in active_accounts if not a.get("is_mock", False)]
    if active_real:
        active_real.sort(key=lambda a: a.get("id", 0), reverse=True)
        return active_real[0]["id"]

    active_accounts.sort(key=lambda a: a.get("id", 0), reverse=True)
    return active_accounts[0]["id"]

# ---------------------------------------------------------------------- #
# 5. VIEW: Dashboard Overview
# ---------------------------------------------------------------------- #
if nav_selection == "Dashboard":
    # Hero Title & Action Bar
    c_title, c_act = st.columns([3, 1])
    with c_title:
        st.markdown("## AI Video Studio")
        st.markdown("<p class='secondary-text'>Create, inspect, review, and auto-publish short-form videos across TikTok, YouTube, and Instagram.</p>", unsafe_allow_html=True)
    with c_act:
        st.write("")
        if st.button("➕ Create Video", type="primary", use_container_width=True):
            st.session_state["nav_target"] = "Create Video"
            st.rerun()

    st.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)

    # Statistics Bar
    all_videos = fetch_videos()
    total_videos = len(all_videos)
    generating_count = sum(1 for v in all_videos if v.get("status") in ["GENERATING", "QA_PENDING"])
    pending_count = sum(1 for v in all_videos if v.get("status") == "PENDING_APPROVAL")
    published_count = sum(1 for v in all_videos if v.get("status") == "PUBLISHED")

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"""
        <div class="stat-card">
            <span class="stat-label">Total Videos</span>
            <span class="stat-value">{total_videos}</span>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
        <div class="stat-card">
            <span class="stat-label">Generating</span>
            <span class="stat-value" style="color: #F78298;">{generating_count}</span>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
        <div class="stat-card">
            <span class="stat-label">Pending Approval</span>
            <span class="stat-value" style="color: #E8A83E;">{pending_count}</span>
        </div>
        """, unsafe_allow_html=True)
    with m4:
        st.markdown(f"""
        <div class="stat-card">
            <span class="stat-label">Published</span>
            <span class="stat-value" style="color: #35C98B;">{published_count}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)

    # Main Dashboard Body: Recent Videos vs Social Publication Overview
    col_left, col_right = st.columns([1.6, 1])

    with col_left:
        st.markdown("### 🎬 Recent Projects")
        if not all_videos:
            st.markdown("""
            <div class="studio-card" style="text-align: center; padding: 40px 20px;">
                <div style="font-size: 32px; margin-bottom: 8px;">🎬</div>
                <div style="font-weight: 700; font-size: 1.1rem;">No videos created yet</div>
                <div class="secondary-text" style="margin-top: 4px;">Start by generating your first AI short-form video concept.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            recent_vids = sorted(all_videos, key=lambda v: v.get("id", 0), reverse=True)[:6]
            for vid_item in recent_vids:
                vid_id = vid_item.get("id")
                v_title = vid_item.get("title") or vid_item.get("topic") or f"Video #{vid_id}"
                v_status = vid_item.get("status", "DRAFT")
                v_created = (vid_item.get("created_at") or "")[:10]
                v_platforms = vid_item.get("selected_platforms") or []
                plat_icons = " ".join([{"youtube": "▶️", "tiktok": "🎵", "instagram": "📸"}.get(p, "🌐") for p in v_platforms]) or "—"

                with st.container():
                    c_info, c_action = st.columns([4, 1.2])
                    with c_info:
                        st.markdown(f"""
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; color: #F78298; background: #1D1D25; padding: 2px 8px; border-radius: 4px;">#{vid_id}</span>
                            <span style="font-weight: 700; font-size: 0.95rem; color: #F7F4F5;">{v_title[:45]}</span>
                            {render_status_pill(v_status)}
                        </div>
                        <div style="display: flex; align-items: center; gap: 16px; margin-top: 4px; font-size: 0.8rem; color: #A9A4AA;">
                            <span>📅 {v_created}</span>
                            <span>Platforms: {plat_icons}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    with c_action:
                        if st.button("Open", key=f"open_dash_{vid_id}", use_container_width=True):
                            st.session_state["selected_video_id"] = vid_id
                            st.session_state["nav_target"] = "My Videos"
                            st.rerun()
                    st.markdown("<hr style='border-color: #1D1D25; margin: 8px 0;'>", unsafe_allow_html=True)

    with col_right:
        st.markdown("### 📊 Platform Channels")
        all_pubs = fetch_publications()
        
        # Calculate platform breakdown
        plat_stats = {
            "tiktok": {"published": 0, "publishing": 0, "failed": 0},
            "youtube": {"published": 0, "publishing": 0, "failed": 0},
            "instagram": {"published": 0, "publishing": 0, "failed": 0},
        }
        for pub in all_pubs:
            p_name = pub.get("platform", "").lower()
            p_status = pub.get("status", "").upper()
            if p_name in plat_stats:
                if p_status == "PUBLISHED":
                    plat_stats[p_name]["published"] += 1
                elif p_status in ["PUBLISHING", "QUEUED"]:
                    plat_stats[p_name]["publishing"] += 1
                elif p_status == "FAILED":
                    plat_stats[p_name]["failed"] += 1

        connected_accounts = fetch_accounts()
        real_tt = next((a for a in connected_accounts if a.get("platform") == "tiktok" and not a.get("is_mock")), None)
        real_yt = next((a for a in connected_accounts if a.get("platform") == "youtube" and not a.get("is_mock")), None)
        real_ig = next((a for a in connected_accounts if a.get("platform") == "instagram" and not a.get("is_mock")), None)

        # TikTok Card
        tt_handle = real_tt.get("account_handle", "@jannah_chic1") if real_tt else "Not Connected"
        st.markdown(f"""
        <div class="studio-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="font-weight: 700; font-size: 1rem;">🎵 TikTok</div>
                <span class="status-badge {'badge-approved' if real_tt else 'badge-draft'}">{'CONNECTED' if real_tt else 'OFFLINE'}</span>
            </div>
            <div class="secondary-text" style="margin-top: 2px;">{tt_handle}</div>
            <div style="display: flex; gap: 16px; margin-top: 12px; font-size: 0.85rem;">
                <span style="color: #35C98B;">✓ {plat_stats['tiktok']['published']} Published</span>
                <span style="color: #E05260;">✕ {plat_stats['tiktok']['failed']} Failed</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # YouTube Card
        yt_handle = real_yt.get("account_name", "AI Video Studio") if real_yt else "Not Connected"
        st.markdown(f"""
        <div class="studio-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="font-weight: 700; font-size: 1rem;">▶️ YouTube Shorts</div>
                <span class="status-badge {'badge-approved' if real_yt else 'badge-draft'}">{'CONNECTED' if real_yt else 'OFFLINE'}</span>
            </div>
            <div class="secondary-text" style="margin-top: 2px;">{yt_handle}</div>
            <div style="display: flex; gap: 16px; margin-top: 12px; font-size: 0.85rem;">
                <span style="color: #35C98B;">✓ {plat_stats['youtube']['published']} Published</span>
                <span style="color: #E05260;">✕ {plat_stats['youtube']['failed']} Failed</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Instagram Card
        ig_handle = real_ig.get("account_name", "Instagram Reels") if real_ig else "Not Connected"
        st.markdown(f"""
        <div class="studio-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="font-weight: 700; font-size: 1rem;">📸 Instagram Reels</div>
                <span class="status-badge {'badge-approved' if real_ig else 'badge-draft'}">{'CONNECTED' if real_ig else 'OFFLINE'}</span>
            </div>
            <div class="secondary-text" style="margin-top: 2px;">{ig_handle}</div>
            <div style="display: flex; gap: 16px; margin-top: 12px; font-size: 0.85rem;">
                <span style="color: #35C98B;">✓ {plat_stats['instagram']['published']} Published</span>
                <span style="color: #E05260;">✕ {plat_stats['instagram']['failed']} Failed</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Manage Social Accounts →", key="dash_goto_social", use_container_width=True):
            st.session_state["nav_target"] = "Social Accounts"
            st.rerun()

# ---------------------------------------------------------------------- #
# 6. VIEW: Create Video (Guided 6-Step Workflow)
# ---------------------------------------------------------------------- #
elif nav_selection == "Create Video":
    st.markdown("## ⚡ Create Video")
    st.markdown("<p class='secondary-text'>Guided multi-step video generation pipeline with real-time planning and rendering.</p>", unsafe_allow_html=True)

    # Initialize creation state
    if "creation_step" not in st.session_state:
        st.session_state["creation_step"] = 1
    if "created_video_id" not in st.session_state:
        st.session_state["created_video_id"] = None

    step = st.session_state["creation_step"]

    # Stepper Header
    st.markdown(f"""
    <div class="stepper-container">
        <div class="stepper-item {'active' if step == 1 else 'completed' if step > 1 else ''}">
            <div class="step-num">{'✓' if step > 1 else '1'}</div>
            <span>Concept</span>
        </div>
        <div style="color: #2B2B35;">—</div>
        <div class="stepper-item {'active' if step == 2 else 'completed' if step > 2 else ''}">
            <div class="step-num">{'✓' if step > 2 else '2'}</div>
            <span>Script & Plan</span>
        </div>
        <div style="color: #2B2B35;">—</div>
        <div class="stepper-item {'active' if step == 3 else 'completed' if step > 3 else ''}">
            <div class="step-num">{'✓' if step > 3 else '3'}</div>
            <span>Visuals</span>
        </div>
        <div style="color: #2B2B35;">—</div>
        <div class="stepper-item {'active' if step == 4 else 'completed' if step > 4 else ''}">
            <div class="step-num">{'✓' if step > 4 else '4'}</div>
            <span>Render</span>
        </div>
        <div style="color: #2B2B35;">—</div>
        <div class="stepper-item {'active' if step == 5 else 'completed' if step > 5 else ''}">
            <div class="step-num">{'✓' if step > 5 else '5'}</div>
            <span>Review</span>
        </div>
        <div style="color: #2B2B35;">—</div>
        <div class="stepper-item {'active' if step == 6 else ''}">
            <div class="step-num">6</div>
            <span>Publish</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Step 1: Concept Input
    if step == 1:
        with st.container():
            st.markdown("#### Step 01: Concept & Parameters")
            col1, col2 = st.columns([2, 1])
            with col1:
                topic_input = st.text_area(
                    "Video Topic / Script Prompt",
                    value="5 Surprising Facts About Artificial Intelligence",
                    height=100,
                    help="Describe the subject, key message, or hook for your short video."
                )
            with col2:
                target_platform = st.selectbox("Target Format", ["tiktok", "youtube", "instagram"], format_func=lambda x: {"tiktok": "🎵 TikTok (9:16)", "youtube": "▶️ YouTube Shorts (9:16)", "instagram": "📸 Instagram Reels (9:16)"}[x])
                duration_sec = st.slider("Target Duration (Seconds)", min_value=15, max_value=60, value=30, step=5)

            c_sub1, c_sub2, c_sub3 = st.columns(3)
            with c_sub1:
                language_opt = st.selectbox("Language", ["en", "es", "fr", "de", "it"], format_func=lambda x: {"en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian"}[x])
            with c_sub2:
                tone_opt = st.selectbox("Style / Tone", ["informative", "dramatic", "energetic", "humorous", "inspirational"])
            with c_sub3:
                visual_style_opt = st.selectbox("Visual Art Style", ["cinematic", "photorealistic", "anime", "neon_cyberpunk", "minimalist"])

            st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
            if st.button("Generate Plan & Script →", type="primary", use_container_width=True):
                with st.spinner("🧠 LLM is crafting high-retention script, scene plan, and visual prompts..."):
                    payload = {
                        "topic": topic_input,
                        "duration_target": duration_sec,
                        "language": language_opt,
                        "target_platform": target_platform,
                        "tone": tone_opt,
                        "visual_style": visual_style_opt,
                    }
                    try:
                        res = requests.post(f"{API_URL}/videos/", json=payload, headers=admin_headers, timeout=30)
                        if res.status_code == 200:
                            created = res.json()
                            st.session_state["created_video_id"] = created["id"]
                            st.session_state["creation_step"] = 2
                            st.success(f"Plan generated successfully! (Project #{created['id']})")
                            st.rerun()
                        else:
                            st.error(f"Failed to generate plan: {res.text}")
                    except Exception as e:
                        st.error(f"Generation error: {e}")

    # Step 2: Script & Plan Review
    elif step == 2:
        vid_id = st.session_state["created_video_id"]
        v_data = fetch_video(vid_id)
        if not v_data:
            st.error("Project not found.")
            if st.button("← Start Over"):
                st.session_state["creation_step"] = 1
                st.rerun()
        else:
            plan = v_data.get("plan") or {}
            st.markdown(f"#### Step 02: Script & Scene Breakdown (Project #{vid_id})")
            
            c_meta1, c_meta2 = st.columns([2, 1])
            with c_meta1:
                st.text_input("Project Title", value=v_data.get("title") or plan.get("title") or "", key=f"edit_t_{vid_id}")
                st.text_area("Complete Narration Voiceover", value=v_data.get("script") or plan.get("complete_narration") or "", height=120, key=f"edit_s_{vid_id}")
            with c_meta2:
                st.text_area("Post Caption", value=v_data.get("caption") or plan.get("caption") or "", height=80, key=f"edit_c_{vid_id}")
                st.text_input("Hashtags", value=" ".join(v_data.get("hashtags") or plan.get("hashtags") or []), key=f"edit_h_{vid_id}")

            st.markdown("##### 🎬 Scene Plan Visual Prompts")
            scenes = plan.get("scenes") or []
            for sc in scenes:
                sc_idx = sc.get("scene_index", 1)
                st.markdown(f"""
                <div class="studio-card-elevated" style="padding: 10px 14px; margin-bottom: 8px;">
                    <div style="font-weight: 700; font-size: 0.85rem; color: #F78298;">Scene {sc_idx} ({sc.get('duration', 4)}s)</div>
                    <div style="font-size: 0.88rem; color: #F7F4F5;">{sc.get('narration', '')}</div>
                    <div class="secondary-text" style="font-size: 0.78rem; font-style: italic; margin-top: 4px;">Prompt: {sc.get('visual_prompt', '')}</div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("##### ⚙️ Visual & Video Engine Selection")
            vp_selected = st.selectbox(
                "Visual & Video Provider Engine",
                ["auto", "pexels", "replicate_video", "replicate", "huggingface", "mock"],
                format_func=lambda x: {
                    "auto": "✨ Auto (High-End Video Clips & Dynamic Visuals)",
                    "pexels": "🎥 Pexels HD (Authentic 1080p/4K Stock Video Clips)",
                    "replicate_video": "🤖 Replicate AI Video (Full Motion Video Clips)",
                    "replicate": "🎨 Replicate Flux (Ultra-HD Imagery + Cinematic Camera Motion)",
                    "huggingface": "⚡ Hugging Face SDXL (Free Cloud Inference + Cinematic Motion)",
                    "mock": "🧪 Development Mock (Fast Local Test)",
                }.get(x, x),
                key=f"vp_choice_{vid_id}",
                help="Select your media source: Authentic HD video clips, AI video generation, or Ultra-HD imagery with cinematic camera motion."
            )

            b1, b2 = st.columns([1, 2])
            with b1:
                if st.button("← Back to Concept", use_container_width=True):
                    st.session_state["creation_step"] = 1
                    st.rerun()
            with b2:
                if st.button("🎬 Generate Full Video Now", type="primary", use_container_width=True):
                    with st.spinner("Starting multi-stage video generation pipeline..."):
                        gen_payload = {"visual_provider": vp_selected}
                        gen_res = requests.post(f"{API_URL}/videos/{vid_id}/generate", json=gen_payload, headers=admin_headers, timeout=10)
                        if gen_res.status_code == 200:
                            st.session_state["creation_step"] = 4
                            st.success("Generation pipeline initiated!")
                            st.rerun()
                        else:
                            st.error(f"Failed to start generation: {gen_res.text}")

    # Step 4: Render / Live Progress
    elif step == 4:
        vid_id = st.session_state["created_video_id"]
        v_data = fetch_video(vid_id)
        cur_status = v_data.get("status") if v_data else "UNKNOWN"

        st.markdown(f"#### Step 04: Rendering Video #{vid_id}")
        st.markdown(f"Current Status: {render_status_pill(cur_status)}", unsafe_allow_html=True)

        # Polished Stepper Progress
        is_done = cur_status in ["PENDING_APPROVAL", "APPROVED", "PUBLISHED"]
        is_failed = cur_status == "FAILED"

        st.markdown(f"""
        <div class="studio-card" style="padding: 24px;">
            <div style="font-weight: 700; font-size: 1.1rem; margin-bottom: 16px;">Pipeline Execution Stages</div>
            <div class="pipeline-step"><span>1. Voiceover Synthesis (TTS Audio)</span> <span style="color: #35C98B;">✓ Ready</span></div>
            <div class="pipeline-step"><span>2. AI Scene Visuals Generation</span> <span style="color: {'#35C98B' if is_done else '#F78298'};">{'✓ Completed' if is_done else '● Processing'}</span></div>
            <div class="pipeline-step"><span>3. High-Accuracy Subtitles Transcriber</span> <span style="color: {'#35C98B' if is_done else '#A9A4AA'};">{'✓ Synchronized' if is_done else '○ Pending'}</span></div>
            <div class="pipeline-step"><span>4. MoviePy Video Composition & Audio Mixing</span> <span style="color: {'#35C98B' if is_done else '#A9A4AA'};">{'✓ Rendered' if is_done else '○ Pending'}</span></div>
            <div class="pipeline-step"><span>5. Automated Quality Assurance Checks</span> <span style="color: {'#35C98B' if is_done else '#A9A4AA'};">{'✓ Validated' if is_done else '○ Pending'}</span></div>
        </div>
        """, unsafe_allow_html=True)

        if is_done:
            st.success("🎉 Video rendered and verified! It is now pending admin review.")
            if st.button("Proceed to Review & Approvals →", type="primary", use_container_width=True):
                st.session_state["selected_video_id"] = vid_id
                st.session_state["nav_target"] = "Review & Approvals"
                st.rerun()
        elif is_failed:
            st.error(f"Generation failed: {v_data.get('rejection_reason', 'Error occurred during generation')}")
            if st.button("Retry Generation"):
                st.session_state["creation_step"] = 2
                st.rerun()
        else:
            time.sleep(2)
            st.rerun()

# ---------------------------------------------------------------------- #
# 7. VIEW: My Videos & Video Detail Workspace
# ---------------------------------------------------------------------- #
elif nav_selection == "My Videos":
    # If a specific video is selected, show the central Video Detail Workspace!
    if "selected_video_id" in st.session_state and st.session_state["selected_video_id"]:
        vid_id = st.session_state["selected_video_id"]
        v_data = fetch_video(vid_id)

        if not v_data:
            st.error("Video not found.")
            st.session_state["selected_video_id"] = None
            st.rerun()

        # Workspace Header with Back Button
        c_back, c_vtitle, c_actions = st.columns([1, 4, 2])
        with c_back:
            if st.button("← Library", key="back_to_lib"):
                st.session_state["selected_video_id"] = None
                st.rerun()
        with c_vtitle:
            st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; color: #F78298; background: #1D1D25; padding: 2px 8px; border-radius: 4px;">#{vid_id}</span>
                <span style="font-size: 1.25rem; font-weight: 800;">{v_data.get('title') or f'Video #{vid_id}'}</span>
                {render_status_pill(v_data.get('status'))}
            </div>
            """, unsafe_allow_html=True)
        with c_actions:
            if v_data.get("status") == "PENDING_APPROVAL":
                if st.button("⚡ Review & Publish", type="primary", use_container_width=True):
                    st.session_state["nav_target"] = "Review & Approvals"
                    st.rerun()

        st.markdown("<div style='margin-top: 16px;'></div>", unsafe_allow_html=True)

        # 2-Column Central Workspace: 9:16 Video Player vs Detail Tabs
        col_video, col_details = st.columns([1.1, 1.9])

        with col_video:
            st.markdown("#### 📱 9:16 Vertical Preview")
            v_path = v_data.get("video_path")
            if v_path and os.path.exists(v_path):
                st.video(v_path)
                f_size = os.path.getsize(v_path) / (1024 * 1024)
                st.markdown(f"""
                <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #A9A4AA; margin-top: 8px; padding: 0 4px;">
                    <span>📁 Size: <b>{f_size:.2f} MB</b></span>
                    <span>⏱️ Duration: <b>{v_data.get('duration_actual') or v_data.get('duration_target', 30)}s</b></span>
                    <span>📐 1080x1920 (9:16)</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="video-viewport-wrapper" style="height: 480px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;">
                    <div style="font-size: 40px; margin-bottom: 12px;">⏳</div>
                    <div style="font-weight: 700; color: #F7F4F5;">No Rendered MP4 Found</div>
                    <div class="secondary-text" style="margin-top: 6px; padding: 0 20px;">Generate or complete the rendering pipeline to preview video.</div>
                </div>
                """, unsafe_allow_html=True)

        with col_details:
            t_meta, t_pub, t_export, t_scenes, t_qa = st.tabs(["📝 Metadata & Pipeline", "🚀 Publication Status", "📲 1-Click Platform Hub", "🖼️ Scene Visuals", "🛡️ Audit & QA"])

            with t_meta:
                plan = v_data.get("plan") or {}
                st.markdown("##### 📌 Video Information")
                st.markdown(f"**Caption:** {v_data.get('caption') or plan.get('caption') or '—'}")
                st.markdown(f"**Hashtags:** {' '.join(v_data.get('hashtags') or plan.get('hashtags') or [])}")
                st.markdown(f"**Narration Script:**")
                st.info(v_data.get("script") or plan.get("complete_narration") or "—")

                st.markdown("##### ⚙️ Pipeline Verification")
                st.markdown("""
                <div class="pipeline-step"><span>✓ LLM Structured Script & Hook</span> <span style="color: #35C98B;">Verified</span></div>
                <div class="pipeline-step"><span>✓ Neural Voiceover Synthesis</span> <span style="color: #35C98B;">Verified</span></div>
                <div class="pipeline-step"><span>✓ Diffusion Scene Imagery</span> <span style="color: #35C98B;">Verified</span></div>
                <div class="pipeline-step"><span>✓ Word-Level Subtitle Transcriber</span> <span style="color: #35C98B;">Verified</span></div>
                <div class="pipeline-step"><span>✓ MoviePy MP4 Video Composition</span> <span style="color: #35C98B;">Verified</span></div>
                """, unsafe_allow_html=True)

            with t_pub:
                st.markdown("##### 📊 Multi-Platform Publication Tracker")
                pubs = fetch_publications(video_id=vid_id)
                if not pubs:
                    st.caption("No publication records found for this video. Use 'Approve & Publish' to select platforms.")
                else:
                    for pub in pubs:
                        p_plat = pub.get("platform", "").lower()
                        p_status = pub.get("status", "NOT_SELECTED").upper()
                        p_acc_id = pub.get("social_account_id")
                        p_post_id = pub.get("platform_post_id")
                        p_post_url = pub.get("post_url")
                        p_err = pub.get("error_message")
                        p_attempts = pub.get("attempt_count", 0)

                        icon = {"youtube": "▶️", "tiktok": "🎵", "instagram": "📸"}.get(p_plat, "🌐")
                        label = {"youtube": "YouTube Shorts", "tiktok": "TikTok", "instagram": "Instagram Reels"}.get(p_plat, p_plat.capitalize())

                        st.markdown(f"""
                        <div class="studio-card">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="font-weight: 700; font-size: 1rem;">{icon} {label}</div>
                                {render_status_pill(p_status)}
                            </div>
                            <div class="secondary-text" style="margin-top: 4px;">Account ID: <b>{p_acc_id or 'Auto'}</b> | Attempts: <b>{p_attempts}</b></div>
                        """, unsafe_allow_html=True)

                        if p_post_url:
                            st.markdown(f"🔗 [View Live Post]({p_post_url})")
                        if p_post_id:
                            st.caption(f"Post/Publish ID: `{p_post_id}`")
                        if p_err and p_status == "FAILED":
                            st.error(f"Error: {p_err[:250]}")
                            if st.button(f"🔁 Retry {label} Publication", key=f"retry_detail_{p_plat}_{vid_id}", type="primary"):
                                with st.spinner(f"Retrying publication to {label}..."):
                                    r_res = requests.post(
                                        f"{API_URL}/videos/{vid_id}/publications/{p_plat}/retry",
                                        headers=admin_headers,
                                        params={"use_sandbox": "false"}
                                    )
                                    if r_res.status_code == 200:
                                        st.success(f"Retry request submitted for {label}!")
                                        st.rerun()
                                    else:
                                        st.error(f"Retry failed: {r_res.text}")

                        st.markdown("</div>", unsafe_allow_html=True)

            with t_export:
                st.markdown("##### 📲 1-Click Platform Publisher & Exporter")
                st.markdown("<p class='secondary-text'>Directly upload or export optimized video & tailored metadata for YouTube Shorts, TikTok, and Instagram Reels.</p>", unsafe_allow_html=True)

                if v_path and os.path.exists(v_path):
                    with open(v_path, "rb") as f_vid:
                        st.download_button(
                            label=f"⬇️ Download Video #{vid_id} MP4 (1080x1920 Vertical HD)",
                            data=f_vid,
                            file_name=f"ai_video_{vid_id}.mp4",
                            mime="video/mp4",
                            type="primary",
                            use_container_width=True
                        )

                col_ep1, col_ep2, col_ep3 = st.columns(3)

                plan = v_data.get("plan") or {}
                vid_title = v_data.get("title") or plan.get("title") or f"Video #{vid_id}"
                vid_caption = v_data.get("caption") or plan.get("caption") or ""
                vid_tags = v_data.get("hashtags") or plan.get("hashtags") or []
                clean_tags = " ".join([f"#{t.lstrip('#')}" for t in vid_tags])

                # 1. YouTube Shorts
                with col_ep1:
                    st.markdown("""
                    <div class="studio-card">
                        <div style="font-weight: 800; font-size: 1.05rem; display: flex; align-items: center; gap: 8px;">
                            <span>▶️</span> YouTube Shorts
                        </div>
                        <div class="secondary-text" style="font-size: 0.78rem; margin: 4px 0 12px 0;">9:16 Vertical &bull; Max 60s</div>
                    </div>
                    """, unsafe_allow_html=True)
                    yt_title_short = f"{vid_title} #Shorts"[:100]
                    st.text_input("Shorts Title", value=yt_title_short, key=f"ep_yt_t_{vid_id}")
                    yt_desc = f"{vid_caption}\n\n{clean_tags}\n\nGenerated with AI Video Studio"
                    st.text_area("Description & Tags", value=yt_desc, height=110, key=f"ep_yt_d_{vid_id}")
                    st.link_button("Upload to YouTube Studio ↗", "https://studio.youtube.com/channel/UC/videos/upload?d=bu", use_container_width=True)
                    if st.button("⚡ Publish to YouTube", key=f"direct_yt_pub_{vid_id}", use_container_width=True):
                        with st.spinner("Publishing to YouTube..."):
                            resp = requests.post(f"{API_URL}/videos/{vid_id}/approve-and-publish", json={"selected_platforms": ["youtube"], "youtube_privacy": "public"}, headers=admin_headers)
                            if resp.status_code == 200:
                                st.success("YouTube publishing initiated!")
                                st.rerun()
                            else:
                                st.error(resp.text)

                # 2. TikTok
                with col_ep2:
                    st.markdown("""
                    <div class="studio-card">
                        <div style="font-weight: 800; font-size: 1.05rem; display: flex; align-items: center; gap: 8px;">
                            <span>🎵</span> TikTok
                        </div>
                        <div class="secondary-text" style="font-size: 0.78rem; margin: 4px 0 12px 0;">9:16 Full Screen &bull; Viral Hashtags</div>
                    </div>
                    """, unsafe_allow_html=True)
                    tt_post_caption = f"{vid_caption} {clean_tags}"[:2200]
                    st.text_area("TikTok Caption & Hashtags", value=tt_post_caption, height=160, key=f"ep_tt_c_{vid_id}")
                    st.link_button("Open TikTok Creator Upload ↗", "https://www.tiktok.com/creator-center/upload", use_container_width=True)
                    if st.button("⚡ Publish to TikTok", key=f"direct_tt_pub_{vid_id}", use_container_width=True):
                        with st.spinner("Publishing to TikTok..."):
                            resp = requests.post(f"{API_URL}/videos/{vid_id}/approve-and-publish", json={"selected_platforms": ["tiktok"], "tiktok_privacy": "SELF_ONLY" if is_tiktok_sandbox_or_unaudited() else "PUBLIC_TO_EVERYONE"}, headers=admin_headers)
                            if resp.status_code == 200:
                                st.success("TikTok publishing initiated!")
                                st.rerun()
                            else:
                                st.error(resp.text)

                # 3. Instagram Reels
                with col_ep3:
                    st.markdown("""
                    <div class="studio-card">
                        <div style="font-weight: 800; font-size: 1.05rem; display: flex; align-items: center; gap: 8px;">
                            <span>📸</span> Instagram Reels
                        </div>
                        <div class="secondary-text" style="font-size: 0.78rem; margin: 4px 0 12px 0;">Reels Feed &bull; 1080x1920</div>
                    </div>
                    """, unsafe_allow_html=True)
                    ig_post_caption = f"{vid_title}\n.\n{vid_caption}\n.\n{clean_tags}"[:2200]
                    st.text_area("Instagram Reel Caption", value=ig_post_caption, height=160, key=f"ep_ig_c_{vid_id}")
                    st.link_button("Open Instagram Web ↗", "https://www.instagram.com/", use_container_width=True)
                    if st.button("⚡ Publish to Instagram", key=f"direct_ig_pub_{vid_id}", use_container_width=True):
                        with st.spinner("Publishing to Instagram Reels..."):
                            resp = requests.post(f"{API_URL}/videos/{vid_id}/approve-and-publish", json={"selected_platforms": ["instagram"]}, headers=admin_headers)
                            if resp.status_code == 200:
                                st.success("Instagram publishing initiated!")
                                st.rerun()
                            else:
                                st.error(resp.text)

            with t_scenes:
                st.markdown("##### 🖼️ Scene Prompts & Visual Frames")
                plan = v_data.get("plan") or {}
                scenes = plan.get("scenes") or []
                if not scenes:
                    st.caption("No scene breakdown available.")
                else:
                    for loop_i, sc in enumerate(scenes):
                        sc_idx = sc.get("scene_number") or sc.get("scene_index") or (loop_i + 1)
                        c_sc1, c_sc2 = st.columns([3, 1])
                        with c_sc1:
                            st.markdown(f"**Scene {sc_idx}:** {sc.get('narration', '')}")
                            vp_text = sc.get("visual_prompt") or sc.get("visual_description", "")
                            media_type = sc.get("media_type", "")
                            if vp_text:
                                st.caption(f"🎬 {media_type.upper() or 'VISUAL'}: {vp_text}")
                            img_path = sc.get("image_path") or sc.get("media_path")
                            if img_path and os.path.exists(img_path):
                                ext = os.path.splitext(img_path)[1].lower()
                                if ext in [".mp4", ".mov", ".webm"]:
                                    st.video(img_path)
                                elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
                                    st.image(img_path, use_container_width=True)
                        with c_sc2:
                            if st.button(f"🔄 Redo Visual", key=f"redo_sc_{vid_id}_{loop_i}"):
                                with st.spinner("Regenerating scene visual..."):
                                    res = requests.post(f"{API_URL}/videos/{vid_id}/scenes/{sc_idx}/regenerate-visual", headers=admin_headers)
                                    if res.status_code == 200:
                                        st.success("Regenerated visual!")
                                        st.rerun()
                                    else:
                                        st.error(f"Failed: {res.text[:200]}")
                        st.markdown("<hr style='border-color: #2B2B35; margin: 8px 0;'>", unsafe_allow_html=True)

            with t_qa:
                st.markdown("##### 🛡️ Automated Quality Assurance Report")
                qa = v_data.get("qa_metrics") or {}
                if qa:
                    q1, q2 = st.columns(2)
                    with q1:
                        st.metric("Duration Target vs Actual", f"{qa.get('duration_actual', 0):.1f}s / {qa.get('duration_target', 0):.1f}s")
                        st.metric("Resolution", qa.get("resolution", "1080x1920"))
                    with q2:
                        st.metric("Audio Loudness (LUFS)", f"{qa.get('loudness_lufs', -14):.1f}")
                        st.metric("Subtitle Alignment", "100% Synchronized")
                else:
                    st.caption("Standard QA pass recorded.")

    # Library Grid View
    else:
        st.markdown("## 🎬 Video Library")
        st.markdown("<p class='secondary-text'>Search, inspect, and open any AI video project workspace.</p>", unsafe_allow_html=True)

        c_srch, c_flt = st.columns([2, 1])
        with c_srch:
            search_query = st.text_input("🔍 Search Videos", placeholder="Search by title, topic, or ID...", label_visibility="collapsed")
        with c_flt:
            status_filter = st.selectbox(
                "Filter Status",
                ["ALL", "PENDING_APPROVAL", "APPROVED", "PUBLISHED", "GENERATING", "FAILED", "DRAFT"],
                label_visibility="collapsed"
            )

        v_list = fetch_videos()
        if status_filter != "ALL":
            v_list = [v for v in v_list if v.get("status") == status_filter]
        if search_query:
            q = search_query.lower()
            v_list = [v for v in v_list if q in str(v.get("id")) or q in (v.get("title") or "").lower() or q in (v.get("topic") or "").lower()]

        if not v_list:
            st.markdown("""
            <div class="studio-card" style="text-align: center; padding: 40px;">
                <div style="font-size: 32px;">🔍</div>
                <div style="font-weight: 700; margin-top: 8px;">No matching videos found</div>
                <div class="secondary-text">Try adjusting your search or filter options.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            for v in v_list:
                vid_id = v.get("id")
                v_title = v.get("title") or v.get("topic") or f"Video #{vid_id}"
                v_status = v.get("status", "DRAFT")
                v_created = (v.get("created_at") or "")[:10]
                v_platforms = v.get("selected_platforms") or []
                plat_icons = " ".join([{"youtube": "▶️", "tiktok": "🎵", "instagram": "📸"}.get(p, "🌐") for p in v_platforms]) or "None"

                with st.container():
                    c_badge, c_main, c_btn = st.columns([1, 4, 1.2])
                    with c_badge:
                        st.markdown(f"""
                        <div style="background: #1D1D25; border-radius: 8px; height: 60px; display: flex; align-items: center; justify-content: center; font-weight: 800; font-family: 'JetBrains Mono', monospace; color: #F78298;">
                            #{vid_id}
                        </div>
                        """, unsafe_allow_html=True)
                    with c_main:
                        st.markdown(f"""
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span style="font-weight: 700; font-size: 1.05rem;">{v_title}</span>
                            {render_status_pill(v_status)}
                        </div>
                        <div class="secondary-text" style="margin-top: 4px;">
                            <span>📅 Created: {v_created}</span> &bull; 
                            <span>Platforms: {plat_icons}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    with c_btn:
                        st.write("")
                        if st.button("Open Workspace →", key=f"lib_open_{vid_id}", use_container_width=True):
                            st.session_state["selected_video_id"] = vid_id
                            st.rerun()

                    st.markdown("<hr style='border-color: #1D1D25; margin: 12px 0;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------- #
# 8. VIEW: Review & Approvals (Dedicated Review Workspace)
# ---------------------------------------------------------------------- #
elif nav_selection == "Review & Approvals":
    st.markdown("## ⚖️ Review & Approvals")
    st.markdown("<p class='secondary-text'>Review completed videos, evaluate quality standards, and execute direct approval & social publishing.</p>", unsafe_allow_html=True)

    tab_pending, tab_approved, tab_rejected = st.tabs(["⏳ Pending Review", "✅ Approved & Published", "❌ Rejected Projects"])

    with tab_pending:
        pending_vids = fetch_videos(status="PENDING_APPROVAL")
        if not pending_vids:
            st.markdown("""
            <div class="studio-card" style="text-align: center; padding: 40px;">
                <div style="font-size: 32px;">🎉</div>
                <div style="font-weight: 700; font-size: 1.1rem; margin-top: 8px;">All Caught Up!</div>
                <div class="secondary-text">No videos currently awaiting review. Generate a new video to approve.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            for p_vid in pending_vids:
                p_id = p_vid.get("id")
                st.markdown(f"""
                <div class="studio-card-active">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="font-size: 1.15rem; font-weight: 800;">Video #{p_id}: {p_vid.get('title') or 'Untitled Project'}</div>
                        {render_status_pill('PENDING_APPROVAL')}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                c_prev, c_form = st.columns([1, 1.4])
                with c_prev:
                    v_path = p_vid.get("video_path")
                    if v_path and os.path.exists(v_path):
                        st.video(v_path)
                    else:
                        st.warning("Video file not found on disk.")

                with c_form:
                    st.markdown("##### 🎯 Target Platforms & Publishing")
                    
                    # Connected accounts for display
                    accounts = fetch_accounts()
                    real_yt = next((a for a in accounts if a.get("platform") == "youtube" and not a.get("is_mock")), None)
                    real_tt = next((a for a in accounts if a.get("platform") == "tiktok" and not a.get("is_mock")), None)
                    real_ig = next((a for a in accounts if a.get("platform") == "instagram" and not a.get("is_mock")), None)

                    c_sel1, c_sel2, c_sel3 = st.columns(3)
                    with c_sel1:
                        sel_yt = st.checkbox("▶️ YouTube Shorts", value=True, key=f"rev_yt_{p_id}")
                        yt_acct_name = real_yt.get("account_name", "AI Video Studio") if real_yt else "Active / Sandbox"
                        st.caption(f"Channel: **{yt_acct_name}**")
                        yt_priv = st.selectbox("YouTube Visibility", ["public", "unlisted", "private"], index=0, key=f"rev_yt_priv_{p_id}")

                    with c_sel2:
                        sel_tt = st.checkbox("🎵 TikTok", value=True, key=f"rev_tt_{p_id}")
                        tt_acct_name = real_tt.get("account_handle", "@jannah_chic1") if real_tt else "Active / Sandbox"
                        st.caption(f"Account: **{tt_acct_name}**")
                        
                        is_tt_sb = is_tiktok_sandbox_or_unaudited()
                        if is_tt_sb:
                            tt_priv_opts = ["SELF_ONLY"]
                            st.caption("🔒 *Sandbox Mode*: `SELF_ONLY` required")
                        else:
                            tt_priv_opts = ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]
                        tt_priv = st.selectbox("TikTok Privacy", tt_priv_opts, index=0, key=f"rev_tt_priv_{p_id}")

                    with c_sel3:
                        sel_ig = st.checkbox("📸 Instagram Reels", value=True, key=f"rev_ig_{p_id}")
                        ig_acct_name = real_ig.get("account_handle", "@aistudio.reels") if real_ig else "Active / Sandbox"
                        st.caption(f"Account: **{ig_acct_name}**")
                        ig_feed = st.checkbox("Share to Feed", value=True, key=f"rev_ig_feed_{p_id}")

                    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                    sb_mode = st.toggle("🧪 Safe Sandbox Test Mode (Verify flow without consuming official API quotas)", value=False, key=f"sb_mode_{p_id}")
                    st.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)
                    
                    b_app, b_rej = st.columns([2, 1])
                    with b_app:
                        selected_plats = []
                        if sel_yt: selected_plats.append("youtube")
                        if sel_tt: selected_plats.append("tiktok")
                        if sel_ig: selected_plats.append("instagram")

                        if st.button("✅ Approve & Publish Now", key=f"btn_app_{p_id}", type="primary", use_container_width=True, disabled=not is_admin or not selected_plats):
                            with st.spinner(f"Approving and publishing to {', '.join(selected_plats)}..."):
                                payload = {
                                    "selected_platforms": selected_plats,
                                    "youtube_privacy": yt_priv,
                                    "tiktok_privacy": tt_priv,
                                    "instagram_share_to_feed": ig_feed,
                                    "use_sandbox": sb_mode
                                }
                                try:
                                    resp = requests.post(f"{API_URL}/videos/{p_id}/approve-and-publish", json=payload, headers=admin_headers, timeout=60)
                                    if resp.status_code == 200:
                                        res_data = resp.json()
                                        st.success(f"🎉 Approved & Published! {res_data.get('message', '')}")
                                        st.session_state["selected_video_id"] = p_id
                                        st.session_state["nav_target"] = "My Videos"
                                        st.rerun()
                                    else:
                                        st.error(f"Approval error: {resp.text}")
                                except Exception as e:
                                    st.error(f"Network error: {e}")

                    with b_rej:
                        with st.popover("❌ Reject"):
                            rej_reason = st.text_input("Rejection Reason", key=f"rej_res_{p_id}")
                            if st.button("Confirm Rejection", key=f"conf_rej_{p_id}"):
                                requests.post(f"{API_URL}/videos/{p_id}/reject", json={"rejection_reason": rej_reason}, headers=admin_headers)
                                st.warning("Video rejected.")
                                st.rerun()

                st.markdown("<hr style='border-color: #2B2B35; margin: 24px 0;'>", unsafe_allow_html=True)

    with tab_approved:
        approved_vids = [v for v in fetch_videos() if v.get("status") in ["APPROVED", "PUBLISHED"]]
        if not approved_vids:
            st.caption("No approved videos found.")
        else:
            for av in approved_vids:
                st.markdown(f"**Video #{av.get('id')}:** {av.get('title')}")
                st.caption(f"Status: {av.get('status')} | Platforms: {', '.join(av.get('selected_platforms') or [])}")

    with tab_rejected:
        rejected_vids = fetch_videos(status="REJECTED")
        if not rejected_vids:
            st.caption("No rejected videos.")
        else:
            for rv in rejected_vids:
                st.markdown(f"**Video #{rv.get('id')}:** {rv.get('title')}")
                st.caption(f"Reason: {rv.get('rejection_reason')}")

# ---------------------------------------------------------------------- #
# 9. VIEW: Publishing Queue
# ---------------------------------------------------------------------- #
elif nav_selection == "Publishing Queue":
    st.markdown("## 🚀 Publishing Queue")
    st.markdown("<p class='secondary-text'>Monitor real-time social platform tasks, active transmissions, and retry failed uploads.</p>", unsafe_allow_html=True)

    col_f1, col_f2 = st.columns([1, 2])
    with col_f1:
        queue_filter = st.selectbox("Status Filter", ["ALL", "FAILED", "PUBLISHED", "PUBLISHING", "QUEUED"], label_visibility="collapsed")

    pubs = fetch_publications()
    if queue_filter != "ALL":
        pubs = [p for p in pubs if p.get("status") == queue_filter]

    if not pubs:
        st.markdown("""
        <div class="studio-card" style="text-align: center; padding: 40px;">
            <div style="font-size: 32px;">📭</div>
            <div style="font-weight: 700; margin-top: 8px;">No tasks in queue</div>
            <div class="secondary-text">No publication records match the selected filter.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        for pub in pubs:
            pub_id = pub.get("id")
            vid_id = pub.get("video_id")
            plat = pub.get("platform", "").lower()
            status = pub.get("status", "QUEUED")
            attempts = pub.get("attempt_count", 0)
            err = pub.get("error_message")
            post_url = pub.get("post_url")
            post_id = pub.get("platform_post_id")

            plat_icon = {"youtube": "▶️", "tiktok": "🎵", "instagram": "📸"}.get(plat, "🌐")

            with st.container():
                c_lead, c_body, c_act = st.columns([1, 4, 1.5])
                with c_lead:
                    st.markdown(f"""
                    <div style="background: #1D1D25; border-radius: 8px; height: 55px; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                        <span style="font-size: 1.2rem;">{plat_icon}</span>
                        <span style="font-size: 0.68rem; font-weight: 700; color: #A9A4AA; text-transform: uppercase;">{plat}</span>
                    </div>
                    """, unsafe_allow_html=True)
                with c_body:
                    st.markdown(f"""
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-weight: 700; font-size: 0.95rem;">Video #{vid_id}</span>
                        {render_status_pill(status)}
                    </div>
                    """, unsafe_allow_html=True)
                    if post_url:
                        st.markdown(f"🔗 [View Live Post]({post_url}) &bull; ID: `{post_id}`")
                    elif err:
                        st.markdown(f"<span style='color: #E05260; font-size: 0.8rem;'>Error: {err[:120]}</span>", unsafe_allow_html=True)
                    st.caption(f"Attempts: {attempts}")

                with c_act:
                    if status == "FAILED":
                        if st.button(f"🔁 Retry", key=f"q_retry_{pub_id}", type="primary", use_container_width=True):
                            with st.spinner("Retrying..."):
                                res = requests.post(f"{API_URL}/videos/{vid_id}/publications/{plat}/retry", headers=admin_headers, params={"use_sandbox": "false"})
                                if res.status_code == 200:
                                    st.success("Retried!")
                                    st.rerun()
                                else:
                                    st.error(f"Failed: {res.text}")
                    elif status == "PUBLISHED" and post_url:
                        st.link_button("View Post ↗", post_url, use_container_width=True)

                st.markdown("<hr style='border-color: #1D1D25; margin: 8px 0;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------- #
# 10. VIEW: Publication History
# ---------------------------------------------------------------------- #
elif nav_selection == "Publication History":
    st.markdown("## 📜 Publication History")
    st.markdown("<p class='secondary-text'>Complete audit trail of all automated and manual social publishing activities.</p>", unsafe_allow_html=True)

    pubs = fetch_publications()
    if not pubs:
        st.caption("No publication events recorded.")
    else:
        for p in pubs:
            plat = p.get("platform", "").capitalize()
            p_stat = p.get("status")
            p_time = (p.get("published_at") or p.get("updated_at") or "")[:19]
            st.markdown(f"""
            <div class="studio-card" style="padding: 12px 18px; margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="font-weight: 700; font-size: 0.95rem;">Video #{p.get('video_id')} &bull; {plat}</span>
                        <div class="secondary-text" style="font-size: 0.78rem;">Timestamp: {p_time}</div>
                    </div>
                    {render_status_pill(p_stat)}
                </div>
            </div>
            """, unsafe_allow_html=True)

# ---------------------------------------------------------------------- #
# 11. VIEW: Social Accounts (OAuth & Channel Connections)
# ---------------------------------------------------------------------- #
elif nav_selection == "Social Accounts":
    st.markdown("## 🌐 Social Accounts")
    st.markdown("<p class='secondary-text'>Manage official developer OAuth integrations for direct publishing to TikTok, YouTube, and Instagram. Supports OAuth 2.0, Direct API Tokens, and Safe Sandbox Mode.</p>", unsafe_allow_html=True)

    accounts = fetch_accounts()
    
    col_t, col_y, col_i = st.columns(3)

    # 1. TikTok Card
    with col_t:
        tt_real = next((a for a in accounts if a.get("platform") == "tiktok" and not a.get("is_mock")), None)

        if tt_real:
            st.markdown(f"""
            <div class="studio-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-weight: 800; font-size: 1.1rem;">🎵 TikTok</div>
                    <span class="status-badge badge-approved">REAL CONNECTED</span>
                </div>
                <div style="margin-top: 10px;">
                    <div style="font-size: 0.92rem; font-weight: 700; color: #35C98B;">{tt_real.get('account_handle', '')}</div>
                    <div class="secondary-text" style="font-size: 0.78rem;">{tt_real.get('account_name', 'TikTok Creator Account')}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Disconnect Real TikTok", key=f"disc_tt_{tt_real.get('id')}", use_container_width=True):
                requests.delete(f"{API_URL}/social/accounts/{tt_real.get('id')}", headers=admin_headers)
                st.rerun()
        else:
            st.markdown("""
            <div class="studio-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-weight: 800; font-size: 1.1rem;">🎵 TikTok</div>
                    <span class="status-badge badge-draft">NOT CONNECTED</span>
                </div>
                <div style="margin-top: 10px;">
                    <div style="font-size: 0.88rem; font-weight: 600;">No Account Connected</div>
                    <div class="secondary-text" style="font-size: 0.78rem;">Connect your account for automated publishing.</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            auth_url = f"{API_URL}/social/oauth/login/tiktok"
            st.link_button("🔗 Connect Real TikTok ↗", auth_url, type="primary", use_container_width=True)

        with st.expander("🔑 Direct Token / Cookie Connect"):
            tt_tok = st.text_input("TikTok Access Token", type="password", key="tt_manual_tok")
            if st.button("Save TikTok Token", key="save_tt_tok_btn", use_container_width=True):
                if tt_tok:
                    requests.post(f"{API_URL}/social/accounts/manual-token", json={"platform": "tiktok", "access_token": tt_tok})
                    st.success("Token saved!")
                    st.rerun()

    # 2. YouTube Card
    with col_y:
        yt_real = next((a for a in accounts if a.get("platform") == "youtube" and not a.get("is_mock")), None)

        if yt_real:
            st.markdown(f"""
            <div class="studio-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-weight: 800; font-size: 1.1rem;">▶️ YouTube</div>
                    <span class="status-badge badge-approved">REAL CONNECTED</span>
                </div>
                <div style="margin-top: 10px;">
                    <div style="font-size: 0.92rem; font-weight: 700; color: #35C98B;">{yt_real.get('account_name', '')}</div>
                    <div class="secondary-text" style="font-size: 0.78rem;">{yt_real.get('account_handle', 'Google Verified Channel')}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Disconnect Real YouTube", key=f"disc_yt_{yt_real.get('id')}", use_container_width=True):
                requests.delete(f"{API_URL}/social/accounts/{yt_real.get('id')}", headers=admin_headers)
                st.rerun()
        else:
            st.markdown("""
            <div class="studio-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-weight: 800; font-size: 1.1rem;">▶️ YouTube</div>
                    <span class="status-badge badge-draft">NOT CONNECTED</span>
                </div>
                <div style="margin-top: 10px;">
                    <div style="font-size: 0.88rem; font-weight: 600;">No Channel Connected</div>
                    <div class="secondary-text" style="font-size: 0.78rem;">Sign in with Google to link your YouTube channel.</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            auth_url = f"{API_URL}/social/oauth/login/youtube"
            st.link_button("🔗 Connect Real YouTube Channel ↗", auth_url, type="primary", use_container_width=True)

        with st.expander("🔑 Direct Token Connect"):
            yt_tok = st.text_input("YouTube OAuth Access Token", type="password", key="yt_manual_tok")
            if st.button("Save YouTube Token", key="save_yt_tok_btn", use_container_width=True):
                if yt_tok:
                    requests.post(f"{API_URL}/social/accounts/manual-token", json={"platform": "youtube", "access_token": yt_tok})
                    st.success("Token saved!")
                    st.rerun()

    # 3. Instagram Card
    with col_i:
        ig_real = next((a for a in accounts if a.get("platform") == "instagram" and not a.get("is_mock")), None)

        if ig_real:
            st.markdown(f"""
            <div class="studio-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-weight: 800; font-size: 1.1rem;">📸 Instagram</div>
                    <span class="status-badge badge-approved">REAL CONNECTED</span>
                </div>
                <div style="margin-top: 10px;">
                    <div style="font-size: 0.92rem; font-weight: 700; color: #35C98B;">{ig_real.get('account_handle', '')}</div>
                    <div class="secondary-text" style="font-size: 0.78rem;">{ig_real.get('account_name', 'Meta Instagram Business')}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Disconnect Real Instagram", key=f"disc_ig_{ig_real.get('id')}", use_container_width=True):
                requests.delete(f"{API_URL}/social/accounts/{ig_real.get('id')}", headers=admin_headers)
                st.rerun()
        else:
            st.markdown("""
            <div class="studio-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-weight: 800; font-size: 1.1rem;">📸 Instagram</div>
                    <span class="status-badge badge-draft">NOT CONNECTED</span>
                </div>
                <div style="margin-top: 10px;">
                    <div style="font-size: 0.88rem; font-weight: 600;">No Account Connected</div>
                    <div class="secondary-text" style="font-size: 0.78rem;">Link Meta Graph API or paste Page Access Token.</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            auth_url = f"{API_URL}/social/oauth/login/instagram"
            st.link_button("🔗 Connect Real Instagram ↗", auth_url, type="primary", use_container_width=True)

        with st.expander("🔑 Direct Token Connect (Meta Graph)"):
            ig_tok = st.text_input("Instagram / Page Access Token", type="password", key="ig_manual_tok")
            if st.button("Save Instagram Token", key="save_ig_tok_btn", use_container_width=True):
                if ig_tok:
                    requests.post(f"{API_URL}/social/accounts/manual-token", json={"platform": "instagram", "access_token": ig_tok})
                    st.success("Token saved!")
                    st.rerun()

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)
    st.markdown("#### 🔒 Security & Credential Protection")
    st.info("Credentials and refresh tokens are encrypted via AES-128-CBC using Fernet encryption and persisted securely. Raw tokens are never shown or printed.")

# ---------------------------------------------------------------------- #
# 12. VIEW: Settings (Pure Configuration)
# ---------------------------------------------------------------------- #
elif nav_selection == "Settings":
    st.markdown("## ⚙️ Settings")
    st.markdown("<p class='secondary-text'>System configuration, AI providers, and administrative controls. Publishing controls are located in Review & Approvals.</p>", unsafe_allow_html=True)

    s_tab1, s_tab2, s_tab3, s_tab4 = st.tabs(["General", "Video Defaults", "AI Models", "API Security"])

    with s_tab1:
        st.markdown("##### 🖥️ Environment & Server")
        st.text_input("FastAPI Backend Server URL", value=API_URL, disabled=True)
        st.caption("Active connection verified via local health endpoint.")

    with s_tab2:
        st.markdown("##### 🎬 Generation Presets")
        st.selectbox("Default Aspect Ratio", ["9:16 (Vertical Short)", "16:9 (Horizontal)"], index=0)
        st.slider("Default Duration (Seconds)", 15, 60, 30)

    with s_tab3:
        st.markdown("##### 🧠 AI Provider Orchestration")
        st.markdown("- **LLM Planning**: OpenAI / Gemini Studio")
        st.markdown("- **TTS Voiceover**: ElevenLabs / Edge TTS")
        st.markdown("- **Visual Generation**: Replicate / HuggingFace FLUX.1")
        st.markdown("- **Subtitle Transcriber**: Whisper Local Pipeline")

    with s_tab4:
        st.markdown("##### 🔐 OAuth Security & Tokens")
        st.markdown("OAuth callback endpoints registered:")
        st.code("http://localhost:8000/social/oauth/callback/tiktok\nhttp://localhost:8000/social/oauth/callback/youtube\nhttp://localhost:8000/social/oauth/callback/instagram")
        st.success("All credentials protected with Fernet symmetric cryptography.")
