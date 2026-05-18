"""Minute.hk Cloud Web App - Streamlit + Supabase + Gemini + Stripe"""
import random
import streamlit as st

import ai
import auth
import cloud_calendar
import cloud_exporters
import cloud_stripe
import dashboard
import db


def _new_captcha():
    """Generate new math captcha question"""
    st.session_state.captcha_a = random.randint(1, 9)
    st.session_state.captcha_b = random.randint(1, 9)
    st.session_state.captcha_op = random.choice(["+", "-"])


def _check_captcha(answer: str) -> bool:
    """Verify captcha answer"""
    try:
        ans_int = int(answer.strip())
    except (ValueError, AttributeError):
        return False
    a = st.session_state.get("captcha_a", 0)
    b = st.session_state.get("captcha_b", 0)
    op = st.session_state.get("captcha_op", "+")
    expected = a + b if op == "+" else a - b
    return ans_int == expected

# ============ Page Config ============
st.set_page_config(
    page_title="Minute.hk - 廣東話會議 AI",
    page_icon="🎙️",
    layout="wide",                     # 等 sidebar + main content 並排展示
    initial_sidebar_state="expanded",  # 登入後默認展開
    menu_items={
        "About": "Minute.hk - 香港人專用 AI 會議摘要工具",
    },
)

# ============ Style - modern card-based design (cyan brand) ============
st.markdown("""
<style>
    /* ============ Global ============ */
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        max-width: 920px;
    }
    .stApp {
        background:
            radial-gradient(900px circle at 0% 0%, rgba(6, 182, 212, 0.04), transparent 50%),
            radial-gradient(700px circle at 100% 100%, rgba(168, 85, 247, 0.03), transparent 50%),
            #fafafa;
    }

    /* ============ Headings ============ */
    h1, h2, h3, h4, h5, h6 { color: #18181b; font-weight: 600; }
    h1 { font-size: 1.4rem !important; }
    h2 { font-size: 1.1rem !important; }
    h3 { font-size: 1rem !important; }
    h4 { font-size: 0.95rem !important; }
    h5 {
        font-size: 0.78rem !important;
        color: #71717a !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 600 !important;
        margin: 1rem 0 0.5rem 0 !important;
    }

    /* ============ Buttons (override Streamlit red default) ============ */
    .stButton button {
        border-radius: 10px;
        font-weight: 500;
        font-size: 0.9rem;
        border: 1px solid #e4e4e7;
        background: white;
        color: #3f3f46;
        transition: all 0.15s;
    }
    .stButton button:hover {
        border-color: #06b6d4;
        color: #06b6d4;
    }
    .stButton button[kind="primary"],
    .stButton button[data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%) !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 12px rgba(6, 182, 212, 0.25) !important;
    }
    .stButton button[kind="primary"]:hover,
    .stButton button[data-testid="baseButton-primary"]:hover {
        background: linear-gradient(135deg, #0891b2 0%, #0e7490 100%) !important;
        box-shadow: 0 6px 16px rgba(6, 182, 212, 0.35) !important;
        transform: translateY(-1px);
    }
    .stFormSubmitButton button[kind="primaryFormSubmit"],
    .stForm button[kind="primary"] {
        background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%) !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
    }

    /* ============ Download buttons ============ */
    .stDownloadButton button {
        background: white;
        border: 1px solid #e4e4e7;
        color: #3f3f46;
        font-size: 0.85rem;
        border-radius: 10px;
    }
    .stDownloadButton button:hover {
        border-color: #06b6d4;
        color: #06b6d4;
    }

    /* ============ Form elements ============ */
    .stTextInput input, .stTextArea textarea {
        border-radius: 10px !important;
        border: 1px solid #e4e4e7 !important;
        padding: 0.55rem 0.85rem !important;
        font-size: 0.9rem !important;
        background: white !important;
        transition: border-color 0.15s, box-shadow 0.15s;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #06b6d4 !important;
        box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.1) !important;
        outline: none !important;
    }
    .stTextInput label, .stSelectbox label, .stTextArea label, .stDateInput label {
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        color: #52525b !important;
        margin-bottom: 0.25rem !important;
    }
    .stSelectbox [data-baseweb="select"] > div {
        border-radius: 10px !important;
        border: 1px solid #e4e4e7 !important;
        background: white !important;
    }
    .stDateInput input {
        border-radius: 10px !important;
        border: 1px solid #e4e4e7 !important;
        background: white !important;
    }

    /* ============ File uploader ============ */
    [data-testid="stFileUploaderDropzone"] {
        padding: 1rem !important;
        min-height: 75px !important;
        border-radius: 12px !important;
        border: 2px dashed #d4d4d8 !important;
        background: rgba(6, 182, 212, 0.02) !important;
        transition: all 0.15s;
    }
    [data-testid="stFileUploaderDropzone"]:hover {
        border-color: #06b6d4 !important;
        background: rgba(6, 182, 212, 0.04) !important;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] { font-size: 0.85rem; }
    [data-testid="stFileUploaderDropzoneInstructions"] > div > small { font-size: 0.72rem; }

    /* ============ Tabs ============ */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        padding: 0;
        border-bottom: 1px solid #e4e4e7;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.5rem 1.2rem;
        font-size: 0.9rem;
        font-weight: 500;
        color: #71717a;
        background: transparent;
        border-radius: 8px 8px 0 0;
    }
    .stTabs [aria-selected="true"] {
        color: #06b6d4 !important;
        font-weight: 600 !important;
    }
    .stTabs [data-baseweb="tab-highlight"] { background: #06b6d4 !important; }
    .stTabs [data-baseweb="tab-panel"] { padding-top: 1rem; }

    /* ============ Expanders (history meetings) ============ */
    [data-testid="stExpander"] {
        border: 1px solid #e4e4e7 !important;
        border-radius: 12px !important;
        background: white !important;
        margin-bottom: 0.5rem;
    }
    [data-testid="stExpanderToggleIcon"] { color: #06b6d4 !important; }

    /* ============ Metrics (dashboard) ============ */
    [data-testid="stMetric"] {
        background: white;
        padding: 1rem 1.2rem;
        border-radius: 12px;
        border: 1px solid #e4e4e7;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
        color: #71717a !important;
        font-weight: 500;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.6rem !important;
        font-weight: 700 !important;
        color: #18181b !important;
    }

    /* ============ Alerts / info boxes ============ */
    .stAlert {
        border-radius: 12px !important;
        border-left: 3px solid #06b6d4 !important;
        font-size: 0.88rem !important;
    }

    /* ============ Captions ============ */
    .stCaption, .stMarkdown small { color: #71717a; font-size: 0.78rem; }

    /* ============ Hide Streamlit chrome ============ */
    header[data-testid="stHeader"] { display: none !important; height: 0 !important; }
    div[data-testid="stToolbar"] { display: none !important; }
    footer { display: none !important; }
    #MainMenu { visibility: hidden; display: none !important; }
    [data-testid="stDecoration"] { display: none !important; }
    .stApp > header { display: none !important; }
    .main .block-container,
    [data-testid="stAppViewBlockContainer"] {
        padding-top: 0.8rem !important;
    }

    /* Misc tightening */
    div[data-testid="stForm"] { border: none; padding: 0; }
    [data-testid="stVerticalBlock"] { gap: 0.5rem !important; }
    .element-container { margin: 0 !important; padding: 0 !important; }

    /* ============ Custom card classes ============ */
    .settings-card {
        background: white;
        border: 1px solid #e4e4e7;
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .settings-card-title {
        font-size: 0.95rem;
        font-weight: 600;
        color: #18181b;
        margin-bottom: 0.2rem;
    }
    .settings-card-desc {
        font-size: 0.78rem;
        color: #71717a;
        margin-bottom: 1rem;
    }

    /* Headings — smaller, more professional */
    h1 {
        font-size: 1.5rem !important;
        color: #1e293b;
        margin-bottom: 0.5rem !important;
        padding-bottom: 0 !important;
        font-weight: 700;
    }
    h2 {
        font-size: 1.15rem !important;
        color: #334155;
        margin-top: 1.2rem !important;
        margin-bottom: 0.4rem !important;
        font-weight: 600;
    }
    h3 {
        font-size: 1rem !important;
        color: #475569;
        margin-top: 0.8rem !important;
    }

    /* Buttons */
    .stButton button {
        border-radius: 8px;
        font-weight: 500;
        border: 1px solid #e2e8f0;
        font-size: 0.9rem;
    }
    .stButton button[kind="primary"] {
        background: #1e66f5;
        border: none;
        color: white;
    }
    .stDownloadButton button {
        border-radius: 8px;
        background: white;
        border: 1px solid #cbd5e1;
        color: #475569;
        font-weight: 500;
    }
    .stDownloadButton button:hover {
        border-color: #1e66f5;
        color: #1e66f5;
    }

    /* === Aggressive: hide ALL Streamlit chrome === */
    header[data-testid="stHeader"] {
        display: none !important;
        height: 0 !important;
    }
    div[data-testid="stToolbar"] { display: none !important; }
    footer { display: none !important; }
    #MainMenu { visibility: hidden; display: none !important; }
    [data-testid="stDecoration"] { display: none !important; }
    .stApp > header { display: none !important; }

    /* Remove top padding from app container */
    .main .block-container,
    [data-testid="stAppViewBlockContainer"] {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
    }

    /* Misc */
    .stAlert { border-radius: 10px; font-size: 0.9rem; }
    div[data-testid="stTabs"] { margin-top: 0 !important; }
    div[data-testid="stForm"] { border: none; padding: 0; }

    /* All vertical blocks tighter */
    [data-testid="stVerticalBlock"] { gap: 0.4rem !important; }
    .element-container { margin: 0 !important; padding: 0 !important; }

    /* Main content max-width (when sidebar展開) */
    .main .block-container { max-width: 900px; }

    /* Sidebar - 唔比 collapse + 靚 styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        border-right: 1px solid #e2e8f0;
        min-width: 260px !important;
        max-width: 280px !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem;
    }
    /* 隱藏 sidebar 嘅 collapse button（強制展開） */
    [data-testid="stSidebarCollapseButton"] {
        display: none !important;
    }
    [data-testid="stSidebarHeader"] {
        padding-bottom: 0 !important;
    }
    /* Sidebar 入面 markdown */
    [data-testid="stSidebar"] .stMarkdown { font-size: 0.88rem; }
    [data-testid="stSidebar"] h5 {
        font-size: 0.85rem !important;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin: 0.8rem 0 0.3rem 0 !important;
    }
    /* Sidebar 嘅 button */
    [data-testid="stSidebar"] .stButton button {
        background: white;
        font-size: 0.85rem;
        padding: 0.4rem 0.8rem;
    }
    [data-testid="stSidebar"] .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #1e66f5 0%, #6366f1 100%);
        color: white;
        border: none;
        box-shadow: 0 2px 8px rgba(30, 102, 245, 0.25);
        font-weight: 600;
    }
    /* Sidebar progress bar */
    [data-testid="stSidebar"] [data-testid="stProgress"] > div > div {
        background: linear-gradient(90deg, #10b981 0%, #1e66f5 100%);
    }
    /* User card */
    .sidebar-user-card {
        background: white;
        padding: 0.8rem;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        margin-bottom: 0.5rem;
    }
    .sidebar-user-name { font-weight: 600; color: #1e293b; font-size: 0.9rem; }
    .sidebar-user-email { color: #64748b; font-size: 0.75rem; word-break: break-all; }
    .sidebar-plan-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 0.7rem;
        font-weight: 700;
        margin-top: 6px;
    }
    .badge-free { background: #eff6ff; color: #1e66f5; }
    .badge-pro { background: #ecfdf5; color: #047857; }
    .badge-team { background: #fef3c7; color: #92400e; }

    /* User info top bar (compact, 一行) */
    .user-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.45rem 1rem;
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        margin-bottom: 0.6rem;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        gap: 1rem;
        flex-wrap: wrap;
    }
    .user-bar-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .user-bar-logo {
        font-size: 1rem;
        font-weight: 700;
        color: #1e293b;
        white-space: nowrap;
    }
    .user-bar-logo span { color: #1e66f5; }
    .user-bar-usage {
        font-size: 0.72rem;
        color: #64748b;
        white-space: nowrap;
    }
    .user-bar-usage strong { color: #1e293b; }
    .user-bar-right { display: flex; align-items: center; gap: 8px; }
    .user-bar-email {
        font-size: 0.78rem;
        color: #475569;
    }
    .user-bar-badge {
        display: inline-block;
        padding: 1px 8px;
        border-radius: 8px;
        font-size: 0.68rem;
        font-weight: 700;
    }
    .badge-free { background: #eff6ff; color: #1e66f5; }
    .badge-pro { background: #ecfdf5; color: #047857; }
    .badge-team { background: #fef3c7; color: #92400e; }
</style>
""", unsafe_allow_html=True)

auth.init_session()

# ============ Handle Stripe redirect ============
qp = st.query_params
if qp.get("upgrade") == "success":
    st.toast("🎉 升級成功！可能要幾分鐘 sync。", icon="✅")
    st.query_params.clear()
elif qp.get("upgrade") == "cancel":
    st.toast("已取消升級", icon="ℹ️")
    st.query_params.clear()

# ============ Auth UI (if not logged in) ============
if not auth.is_logged_in():
    st.markdown(
        "<h2 style='text-align:center;margin:1rem 0 0 0;'>🎙️ Minute.hk</h2>"
        "<p style='text-align:center;color:#64748b;margin:0.2rem 0 0.8rem 0;font-size:0.85rem;'>"
        "廣東話會議 AI 摘要 · 香港人專用</p>",
        unsafe_allow_html=True,
    )

    tab_login, tab_signup, tab_reset = st.tabs(["🔓 登入", "✨ 註冊", "🔑 忘記密碼"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="you@example.com", label_visibility="collapsed")
            password = st.text_input("Password", type="password", placeholder="密碼", label_visibility="collapsed")
            submit = st.form_submit_button("登入", type="primary", use_container_width=True)
            if submit:
                if not email or not password:
                    st.error("請填 email 同密碼")
                else:
                    ok, msg = auth.login(email, password)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    with tab_signup:
        # Init captcha (一次性 per session)
        if "captcha_a" not in st.session_state:
            _new_captcha()

        with st.form("signup_form"):
            email = st.text_input("Email", placeholder="you@example.com",
                                  key="su_email", label_visibility="collapsed")
            password = st.text_input("Password", type="password", placeholder="密碼（至少 6 位）",
                                     key="su_pass", label_visibility="collapsed")
            password2 = st.text_input("Confirm", type="password", placeholder="確認密碼",
                                      key="su_pass2", label_visibility="collapsed")
            # 🤖 Math captcha 防 bot
            a = st.session_state.captcha_a
            b = st.session_state.captcha_b
            op = st.session_state.captcha_op
            captcha_ans = st.text_input(
                "驗證碼",
                placeholder=f"🤖 防 bot 驗證：{a} {op} {b} = ?",
                key="captcha_input",
                label_visibility="collapsed",
            )
            submit = st.form_submit_button("✨ 免費註冊", type="primary", use_container_width=True)
            if submit:
                if not email or not password:
                    st.error("請填 email 同密碼")
                elif password != password2:
                    st.error("兩次密碼唔同")
                elif not _check_captcha(captcha_ans):
                    st.error(f"驗證碼錯誤。{a} {op} {b} = ?")
                    _new_captcha()
                else:
                    ok, msg = auth.signup(email, password)
                    if ok:
                        st.success(msg)
                        _new_captcha()  # Refresh captcha
                        if "正在登入" in msg:
                            st.rerun()
                    else:
                        st.error(msg)
                        _new_captcha()

    with tab_reset:
        with st.form("reset_form"):
            email = st.text_input("Email", key="rp_email",
                                  placeholder="你註冊嘅 email", label_visibility="collapsed")
            submit = st.form_submit_button("📧 寄重設密碼 link", use_container_width=True)
            if submit and email:
                ok, msg = auth.reset_password(email)
                (st.success if ok else st.error)(msg)

    st.markdown(
        "<p style='text-align:center;font-size:0.78rem;color:#94a3b8;margin-top:1rem;'>"
        "<a href='https://minutehk.vercel.app' style='color:#1e66f5;text-decoration:none;'>← 返主頁</a>"
        "&nbsp;·&nbsp;免費版 30 分鐘/月</p>",
        unsafe_allow_html=True,
    )

    st.stop()

# ============ Logged in - Main App ============
user = auth.get_user()
plan = db.get_user_plan(user["id"])
plan_emoji = {"free": "🆓", "pro": "⭐", "team": "👥"}.get(plan, "🆓")
plan_badge_class = {"free": "badge-free", "pro": "badge-pro", "team": "badge-team"}.get(plan, "badge-free")

# === Compute usage for top bar ===
monthly_used = db.get_monthly_usage_seconds(user["id"]) / 60
daily_used = db.get_daily_usage_seconds(user["id"]) / 60
if plan == "free":
    monthly_limit_str = f"{db.FREE_MONTHLY_SECONDS / 60:.0f}"
    daily_limit_str = f"{db.FREE_DAILY_SECONDS / 60:.0f}"
else:
    monthly_limit_str = "∞"
    daily_limit_str = f"{db.PRO_DAILY_SECONDS / 60:.0f}"

# === Top User Bar (主畫面上方) ===
st.markdown(f"""
<div class="user-bar">
    <div class="user-bar-left">
        <div class="user-bar-logo">🎙️ Minute<span>.hk</span></div>
        <div class="user-bar-usage">
            📊 今日 <strong>{daily_used:.1f}/{daily_limit_str}</strong> 分鐘
            · 本月 <strong>{monthly_used:.1f}/{monthly_limit_str}</strong> 分鐘
        </div>
    </div>
    <div class="user-bar-right">
        <div class="user-bar-email">👋 {user["email"]}</div>
        <span class="user-bar-badge {plan_badge_class}">{plan_emoji} {plan.upper()}</span>
    </div>
</div>
""", unsafe_allow_html=True)

# === Sidebar (簡化版：只係快速連結 + 登出) ===
with st.sidebar:
    st.markdown(
        "<div style='font-size:1.05rem;font-weight:700;color:#1e293b;padding:0.3rem 0 1rem 0;'>"
        "🎙️ Minute<span style='color:#1e66f5;'>.hk</span></div>",
        unsafe_allow_html=True,
    )

    st.markdown("##### 🔗 快速連結")
    st.markdown(
        "<a href='https://minutehk.vercel.app' target='_blank' "
        "style='color:#1e66f5;text-decoration:none;font-size:0.85rem;display:block;padding:4px 0;'>"
        "🏠 主頁</a>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<a href='https://minutehk.vercel.app/#faq' target='_blank' "
        "style='color:#1e66f5;text-decoration:none;font-size:0.85rem;display:block;padding:4px 0;'>"
        "❓ 常見問題</a>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<a href='mailto:xavierchow61@gmail.com' "
        "style='color:#1e66f5;text-decoration:none;font-size:0.85rem;display:block;padding:4px 0;'>"
        "📧 聯絡支援</a>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)
    if st.button("🚪 登出", use_container_width=True):
        auth.logout()
        st.rerun()

# Load user settings (used by 新會議 + 設定 tab)
user_settings = db.get_user_settings(user["id"])

# Main content tabs
tab_new, tab_history, tab_dashboard, tab_settings = st.tabs([
    "🎙️ 新會議", "📚 過往會議", "📊 Dashboard", "⚙️ 設定"
])

# ============ Tab 1: New Meeting ============
with tab_new:
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        client_name = st.text_input("客戶", placeholder="ABC Limited",
                                    label_visibility="collapsed")
    with col2:
        project_name = st.text_input("項目", placeholder="2026 audit",
                                     label_visibility="collapsed")
    with col3:
        # 紀要長度 selector (default 用 user settings)
        length_keys = list(db.SUMMARY_LENGTHS.keys())
        default_length = user_settings.get("summary_length", "medium")
        try:
            default_idx = length_keys.index(default_length)
        except ValueError:
            default_idx = 1
        summary_length = st.selectbox(
            "長度",
            options=length_keys,
            format_func=lambda k: db.SUMMARY_LENGTHS[k].split("（")[0],
            index=default_idx,
            label_visibility="collapsed",
            key="meeting_length",
        )

    # 兩個 input 方法 tabs
    in_tab_upload, in_tab_record = st.tabs(["📁 上傳檔案", "🎙️ 直接錄音"])

    with in_tab_upload:
        uploaded = st.file_uploader(
            "上傳會議錄音",
            type=["mp3", "m4a", "wav", "mp4", "ogg", "flac", "webm"],
            help="支援 mp3/m4a/wav/mp4/ogg/flac/webm，最大 200MB",
            label_visibility="collapsed",
            key="audio_upload",
        )

    with in_tab_record:
        recorded = st.audio_input(
            "🎙️ 撳下面 mic 開始錄音",
            key="audio_record",
            label_visibility="collapsed",
        )

    # 揀邊個 input source
    audio_source = uploaded or recorded
    is_recording = recorded is not None and uploaded is None

    if audio_source:
        if is_recording:
            file_size_mb = len(audio_source.getvalue()) / (1024 * 1024)
            st.caption(f"🎙️ 錄音 · {file_size_mb:.1f} MB")
        else:
            file_size_mb = audio_source.size / (1024 * 1024)
            st.caption(f"📄 `{audio_source.name}` · {file_size_mb:.1f} MB")
        st.audio(audio_source)

        # local var name 為咗下面 code 兼容
        uploaded = audio_source

        est_duration_sec = file_size_mb * 60

        can_process_now, msg = db.can_process(user["id"], est_duration_sec)
        if not can_process_now:
            st.error(msg)
        else:
            if st.button("🚀 開始 AI 處理", type="primary", use_container_width=True):
                with st.status("🤖 AI 處理中...", expanded=True) as status:
                    try:
                        mime_type = uploaded.type or "audio/mpeg"
                        audio_bytes = uploaded.read()
                        st.write("🎯 上傳到 Gemini...")

                        result = ai.process_audio(
                            audio_bytes=audio_bytes,
                            mime_type=mime_type,
                            client_name=client_name,
                            project_name=project_name,
                            industry=user_settings.get("industry", "generic"),
                            length=summary_length,
                            custom_jargon=user_settings.get("jargon", ""),
                            company_name=user_settings.get("company_name", ""),
                        )
                        st.write("✅ AI 整理完成")
                        st.write("💾 儲存到資料庫...")
                        saved = db.save_meeting(
                            user_id=user["id"],
                            summary=result["summary"],
                            client=client_name or None,
                            project=project_name or None,
                            duration_seconds=est_duration_sec,
                            audio_filename=uploaded.name,
                        )
                        st.write("✅ 已儲存")
                        status.update(label="✅ 完成！", state="complete")

                        st.session_state.last_summary = result["summary"]
                        st.session_state.last_meeting_name = client_name or "會議"
                        # 新 meeting → reset 之前嘅翻譯/語氣 cache
                        st.session_state.pop("last_translation", None)
                        st.session_state.pop("last_translation_lang", None)
                        st.session_state.pop("last_sentiment", None)

                    except Exception as e:
                        err_msg = str(e)
                        if "\\x" in err_msg or err_msg.startswith("b'"):
                            err_msg = "錄音處理失敗，請試吓另一個檔案。"
                        elif len(err_msg) > 300:
                            err_msg = err_msg[:300] + "..."
                        st.error(f"❌ {err_msg}")
                        with st.expander("🔍 技術詳情"):
                            st.exception(e)

    # 顯示最後一次嘅 summary + download buttons + translate + sentiment
    if st.session_state.get("last_summary"):
        st.divider()
        st.markdown("#### 📝 會議紀要")
        st.markdown(st.session_state.last_summary)

        st.markdown("##### 📥 下載")
        col_md, col_word, col_pdf, col_ics = st.columns(4)
        base_name = st.session_state.get("last_meeting_name", "meeting").replace(" ", "_")

        with col_md:
            st.download_button(
                "📝 Markdown",
                st.session_state.last_summary,
                file_name=f"{base_name}_紀要.md",
                mime="text/markdown",
                use_container_width=True,
            )

        with col_word:
            try:
                docx_bytes = cloud_exporters.md_to_docx_bytes(st.session_state.last_summary)
                st.download_button(
                    "📄 Word",
                    docx_bytes,
                    file_name=f"{base_name}_紀要.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            except Exception as e:
                st.button("📄 Word (錯)", disabled=True, use_container_width=True, help=str(e))

        with col_pdf:
            try:
                pdf_bytes = cloud_exporters.md_to_pdf_bytes(st.session_state.last_summary)
                st.download_button(
                    "📕 PDF",
                    pdf_bytes,
                    file_name=f"{base_name}_紀要.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.button("📕 PDF (錯)", disabled=True, use_container_width=True, help=str(e))

        with col_ics:
            # 📅 ICS file (Calendar export)
            if st.button("📅 加入 Calendar", use_container_width=True, key="ics_main"):
                with st.spinner("AI 抽取 action items..."):
                    try:
                        items = ai.extract_action_items(st.session_state.last_summary)
                        if not items:
                            st.warning("冇 action items 可以加入 calendar")
                        else:
                            ics_bytes = cloud_calendar.action_items_to_ics(
                                items,
                                meeting_title=base_name,
                                client=st.session_state.get("last_meeting_name", ""),
                            )
                            st.session_state.ics_main = ics_bytes
                            st.session_state.ics_main_count = len(items)
                    except Exception as e:
                        st.error(f"ICS 生成失敗：{e}")

        if st.session_state.get("ics_main"):
            cnt = st.session_state.get("ics_main_count", 0)
            st.download_button(
                f"📥 下載 .ics ({cnt} 個事項)",
                st.session_state.ics_main,
                file_name=f"{base_name}_calendar.ics",
                mime="text/calendar",
                key="dl_ics_main",
            )
            st.caption("💡 Double-click `.ics` → 自動 import 入 Google Calendar / Outlook / Apple Calendar")

        # === 🌐 翻譯 + 🎭 語氣分析 ===
        st.markdown("##### 🤖 AI 進階分析")

        col_t, col_s = st.columns(2)

        # --- Translate ---
        with col_t:
            target_label = st.selectbox(
                "🌐 翻譯紀要",
                options=list(ai.TRANSLATE_TARGETS.values()),
                key="translate_target",
                label_visibility="collapsed",
            )
            if st.button("🌐 翻譯", use_container_width=True, key="btn_translate"):
                # 揾返 target code
                target_code = next(
                    (k for k, v in ai.TRANSLATE_TARGETS.items() if v == target_label),
                    "en"
                )
                with st.spinner(f"翻譯成 {target_label}..."):
                    try:
                        translated = ai.translate(st.session_state.last_summary, target_code)
                        st.session_state.last_translation = translated
                        st.session_state.last_translation_lang = target_label
                    except Exception as e:
                        st.error(f"翻譯失敗：{e}")

        # --- Sentiment ---
        with col_s:
            st.markdown(
                "<div style='height:38px;display:flex;align-items:center;color:#64748b;font-size:0.85rem;'>"
                "🎭 分析會議語氣 + 風險信號"
                "</div>",
                unsafe_allow_html=True,
            )
            if st.button("🎭 語氣分析", use_container_width=True, key="btn_sentiment"):
                with st.spinner("AI 分析中..."):
                    try:
                        sentiment = ai.analyze_sentiment(st.session_state.last_summary)
                        st.session_state.last_sentiment = sentiment
                    except Exception as e:
                        st.error(f"分析失敗：{e}")

        # 顯示翻譯結果
        if st.session_state.get("last_translation"):
            with st.expander(f"🌐 {st.session_state.get('last_translation_lang', '翻譯')} 譯本", expanded=True):
                st.markdown(st.session_state.last_translation)
                st.download_button(
                    "📥 下載譯本 (Markdown)",
                    st.session_state.last_translation,
                    file_name=f"{base_name}_translated.md",
                    mime="text/markdown",
                    key="dl_translated",
                )

        # 顯示語氣分析結果
        if st.session_state.get("last_sentiment"):
            with st.expander("🎭 語氣分析報告", expanded=True):
                st.markdown(st.session_state.last_sentiment)
                st.download_button(
                    "📥 下載語氣報告 (Markdown)",
                    st.session_state.last_sentiment,
                    file_name=f"{base_name}_sentiment.md",
                    mime="text/markdown",
                    key="dl_sentiment",
                )

# ============ Tab 2: History (with Search + Date Filter) ============
with tab_history:
    # 🔍 Compact filter row: Search (60%) | From (20%) | To (20%)
    f_col_q, f_col_from, f_col_to = st.columns([3, 1, 1])

    with f_col_q:
        search_query = st.text_input(
            "搜尋",
            placeholder="🔍 搜尋客戶、項目、紀要內容、文字稿...",
            label_visibility="collapsed",
            key="search_query",
        )

    with f_col_from:
        date_from = st.date_input(
            "📅 由",
            value=None,
            key="search_date_from",
            format="YYYY-MM-DD",
            label_visibility="collapsed",
        )

    with f_col_to:
        date_to = st.date_input(
            "📅 到",
            value=None,
            key="search_date_to",
            format="YYYY-MM-DD",
            label_visibility="collapsed",
        )

    # Determine if any filter active
    has_filter = bool(search_query) or date_from is not None or date_to is not None

    if has_filter:
        meetings = db.search_meetings(
            user["id"],
            query=search_query,
            date_from=date_from,
            date_to=date_to,
            limit=100,
        )
        # 建 filter description
        filter_parts = []
        if search_query:
            filter_parts.append(f"搜「**{search_query}**」")
        if date_from:
            filter_parts.append(f"由 **{date_from}**")
        if date_to:
            filter_parts.append(f"到 **{date_to}**")
        filter_desc = " · ".join(filter_parts)

        if meetings:
            st.caption(f"🔍 {filter_desc} · 揾到 **{len(meetings)}** 個會議")
        else:
            st.warning(f"🔍 {filter_desc} · 冇 meeting match")
            st.stop()
    else:
        meetings = db.list_meetings(user["id"], limit=50)
        if meetings:
            st.caption(f"📚 共 {len(meetings)} 個 meeting（最近 50 個）")

    if not meetings:
        st.info("仲未有任何會議紀錄。上面 tab 上傳第一個錄音啦！")
    else:
        for m in meetings:
            date = m["created_at"][:16].replace("T", " ")
            client = m.get("client") or "—"
            project = m.get("project") or "—"
            duration_min = (m.get("duration_seconds") or 0) / 60

            # 顯示時 highlight match
            title = f"📅 {date} · {client} / {project} · {duration_min:.1f} 分鐘"

            with st.expander(title):
                full = db.get_meeting(m["id"], user["id"])
                if full:
                    st.markdown(full["summary"])
                    col_md, col_word, col_pdf, col_del = st.columns([1, 1, 1, 1])
                    base_name = (client or "meeting").replace(" ", "_")

                    with col_md:
                        st.download_button(
                            "📝 MD",
                            full["summary"],
                            file_name=f"{base_name}_紀要.md",
                            mime="text/markdown",
                            key=f"md_{m['id']}",
                            use_container_width=True,
                        )
                    with col_word:
                        try:
                            docx_bytes = cloud_exporters.md_to_docx_bytes(full["summary"])
                            st.download_button(
                                "📄 Word",
                                docx_bytes,
                                file_name=f"{base_name}_紀要.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                key=f"docx_{m['id']}",
                                use_container_width=True,
                            )
                        except Exception:
                            pass
                    with col_pdf:
                        try:
                            pdf_bytes = cloud_exporters.md_to_pdf_bytes(full["summary"])
                            st.download_button(
                                "📕 PDF",
                                pdf_bytes,
                                file_name=f"{base_name}_紀要.pdf",
                                mime="application/pdf",
                                key=f"pdf_{m['id']}",
                                use_container_width=True,
                            )
                        except Exception:
                            pass
                    with col_del:
                        if st.button("🗑️ 刪除", key=f"del_{m['id']}", use_container_width=True):
                            db.delete_meeting(m["id"], user["id"])
                            st.rerun()

                    # === 🤖 AI 進階分析（每個 meeting）===
                    st.markdown("**🤖 AI 進階分析**")
                    h_col_t, h_col_s = st.columns(2)

                    # --- Translate ---
                    with h_col_t:
                        target_label = st.selectbox(
                            "翻譯為",
                            options=list(ai.TRANSLATE_TARGETS.values()),
                            key=f"h_tr_target_{m['id']}",
                            label_visibility="collapsed",
                        )
                        if st.button(
                            "🌐 翻譯紀要",
                            key=f"h_btn_tr_{m['id']}",
                            use_container_width=True,
                        ):
                            target_code = next(
                                (k for k, v in ai.TRANSLATE_TARGETS.items()
                                 if v == target_label),
                                "en",
                            )
                            with st.spinner(f"翻譯成 {target_label}..."):
                                try:
                                    translated = ai.translate(full["summary"], target_code)
                                    st.session_state[f"h_tr_{m['id']}"] = translated
                                    st.session_state[f"h_tr_lang_{m['id']}"] = target_label
                                except Exception as e:
                                    st.error(f"翻譯失敗：{e}")

                    # --- Sentiment ---
                    with h_col_s:
                        st.markdown(
                            "<div style='height:38px;display:flex;align-items:center;"
                            "color:#64748b;font-size:0.82rem;'>"
                            "🎭 分析會議語氣 + 風險"
                            "</div>",
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            "🎭 語氣分析",
                            key=f"h_btn_sent_{m['id']}",
                            use_container_width=True,
                        ):
                            with st.spinner("分析中..."):
                                try:
                                    sent = ai.analyze_sentiment(full["summary"])
                                    st.session_state[f"h_sent_{m['id']}"] = sent
                                except Exception as e:
                                    st.error(f"分析失敗：{e}")

                    # --- 顯示翻譯結果 ---
                    if st.session_state.get(f"h_tr_{m['id']}"):
                        lang_label = st.session_state.get(
                            f"h_tr_lang_{m['id']}", "翻譯"
                        )
                        with st.expander(f"🌐 {lang_label} 譯本", expanded=True):
                            st.markdown(st.session_state[f"h_tr_{m['id']}"])
                            st.download_button(
                                "📥 下載譯本",
                                st.session_state[f"h_tr_{m['id']}"],
                                file_name=f"{base_name}_translated.md",
                                mime="text/markdown",
                                key=f"h_dl_tr_{m['id']}",
                            )

                    # --- 顯示語氣分析結果 ---
                    if st.session_state.get(f"h_sent_{m['id']}"):
                        with st.expander("🎭 語氣分析報告", expanded=True):
                            st.markdown(st.session_state[f"h_sent_{m['id']}"])
                            st.download_button(
                                "📥 下載語氣報告",
                                st.session_state[f"h_sent_{m['id']}"],
                                file_name=f"{base_name}_sentiment.md",
                                mime="text/markdown",
                                key=f"h_dl_sent_{m['id']}",
                            )

                    # === 📅 Calendar export + 🔗 Continue meeting ===
                    st.markdown("**📅 Calendar + 🔗 繼續會議**")
                    h_col_ics, h_col_cont = st.columns(2)

                    with h_col_ics:
                        if st.button(
                            "📅 加入 Calendar",
                            key=f"h_btn_ics_{m['id']}",
                            use_container_width=True,
                        ):
                            with st.spinner("AI 抽取 action items..."):
                                try:
                                    items = ai.extract_action_items(full["summary"])
                                    if not items:
                                        st.warning("冇 action items 可以加入")
                                    else:
                                        ics_b = cloud_calendar.action_items_to_ics(
                                            items,
                                            meeting_title=base_name,
                                            client=client,
                                        )
                                        st.session_state[f"h_ics_{m['id']}"] = ics_b
                                        st.session_state[f"h_ics_count_{m['id']}"] = len(items)
                                except Exception as e:
                                    st.error(f"失敗：{e}")

                    with h_col_cont:
                        if st.button(
                            "🔗 繼續呢個會議",
                            key=f"h_btn_cont_{m['id']}",
                            use_container_width=True,
                        ):
                            st.session_state[f"h_cont_open_{m['id']}"] = True

                    # ICS download
                    if st.session_state.get(f"h_ics_{m['id']}"):
                        cnt = st.session_state.get(f"h_ics_count_{m['id']}", 0)
                        st.download_button(
                            f"📥 下載 .ics ({cnt} 個事項)",
                            st.session_state[f"h_ics_{m['id']}"],
                            file_name=f"{base_name}_calendar.ics",
                            mime="text/calendar",
                            key=f"h_dl_ics_{m['id']}",
                        )

                    # Continue meeting UI
                    if st.session_state.get(f"h_cont_open_{m['id']}"):
                        with st.expander("🔗 上傳/錄新會議 → AI 合併", expanded=True):
                            st.caption("上傳新一段錄音，AI 會將呢個會議同新嘅合併。")

                            cont_uploaded = st.file_uploader(
                                "新錄音",
                                type=["mp3", "m4a", "wav", "mp4", "ogg", "flac", "webm"],
                                key=f"h_cont_upload_{m['id']}",
                                label_visibility="collapsed",
                            )

                            if cont_uploaded:
                                cont_size_mb = cont_uploaded.size / (1024 * 1024)
                                st.caption(f"📄 `{cont_uploaded.name}` · {cont_size_mb:.1f} MB")

                                if st.button(
                                    "🚀 處理 + 合併",
                                    type="primary",
                                    key=f"h_cont_go_{m['id']}",
                                    use_container_width=True,
                                ):
                                    with st.status("🤖 處理 + 合併中...", expanded=True) as cs:
                                        try:
                                            st.write("🎯 AI 處理新錄音...")
                                            new_result = ai.process_audio(
                                                audio_bytes=cont_uploaded.read(),
                                                mime_type=cont_uploaded.type or "audio/mpeg",
                                                client_name=client,
                                                project_name=project,
                                                industry=user_settings.get("industry", "generic"),
                                                length=user_settings.get("summary_length", "medium"),
                                                custom_jargon=user_settings.get("jargon", ""),
                                                company_name=user_settings.get("company_name", ""),
                                            )
                                            st.write("✅ 新會議處理完成")

                                            st.write("🔗 AI 合併紀要...")
                                            merged = ai.merge_summaries(
                                                old_summary=full["summary"],
                                                new_summary=new_result["summary"],
                                            )
                                            st.write("💾 儲存合併版本...")

                                            db.update_meeting_summary(
                                                meeting_id=m["id"],
                                                user_id=user["id"],
                                                new_summary=merged,
                                                additional_duration=cont_size_mb * 60,
                                            )
                                            st.write("✅ 完成")
                                            cs.update(label="✅ 已合併", state="complete")

                                            st.session_state.pop(f"h_cont_open_{m['id']}", None)
                                            st.success("🎉 兩個會議已合併！refresh 睇下。")
                                            if st.button("🔄 Refresh",
                                                         key=f"h_cont_refresh_{m['id']}"):
                                                st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ 合併失敗：{e}")


# ============ Tab 3: Dashboard ============
with tab_dashboard:
    stats = db.get_dashboard_stats(user["id"])

    if stats["total_count"] == 0:
        st.info("📊 仲未有任何會議。上面 tab 上傳第一個錄音先有 dashboard！")
    else:
        # === Top stats cards ===
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("📚 總會議", f"{stats['total_count']}")
        col_b.metric("⏱️ 總時長", f"{stats['total_hours']:.1f} 小時")
        avg_min = stats["total_minutes"] / stats["total_count"] if stats["total_count"] else 0
        col_c.metric("📏 平均長度", f"{avg_min:.1f} 分鐘")
        col_d.metric("👥 客戶數", f"{len(stats['top_clients'])}")

        st.markdown("---")

        # === Monthly trend ===
        st.markdown("##### 📈 每月會議數量")
        if stats["monthly_counts"] and len(stats["monthly_counts"]) > 1:
            import pandas as pd
            df_trend = pd.DataFrame({
                "月份": list(stats["monthly_counts"].keys()),
                "會議數": list(stats["monthly_counts"].values()),
            })
            st.bar_chart(
                df_trend.set_index("月份"),
                height=240,
                color="#1e66f5",
            )
        elif stats["monthly_counts"]:
            # 只得 1 個月嘅數據 → 顯示 inline metric (chart 太醜)
            month, count = next(iter(stats["monthly_counts"].items()))
            st.info(f"📅 **{month}**：{count} 個 meeting（要至少 2 個月先有 trend chart）")
        else:
            st.caption("（暫時冇數據）")

        # === Top clients + projects ===
        col_left, col_right = st.columns(2)
        with col_left:
            st.markdown("##### 🥇 Top 客戶")
            if stats["top_clients"]:
                for i, (client, count) in enumerate(stats["top_clients"][:5], 1):
                    st.write(f"{i}. **{client}** — {count} 個 meeting")
            else:
                st.caption("（暫時冇 client tag）")

        with col_right:
            st.markdown("##### 📂 Top 項目")
            if stats["top_projects"]:
                for i, (proj, count) in enumerate(stats["top_projects"][:5], 1):
                    st.write(f"{i}. **{proj}** — {count} 個 meeting")
            else:
                st.caption("（暫時冇 project tag）")

        # === Word Cloud ===
        st.markdown("---")
        st.markdown("##### ☁️ 詞雲 (Top Keywords)")
        if st.button("🔄 生成詞雲", key="gen_wordcloud"):
            with st.spinner("分析所有會議文字..."):
                try:
                    img_bytes = dashboard.generate_wordcloud_image(
                        stats["all_summaries_text"], max_words=80
                    )
                    if img_bytes:
                        st.session_state.wordcloud_img = img_bytes
                    else:
                        # Fallback: text list
                        keywords = dashboard.extract_keywords(
                            stats["all_summaries_text"], top_n=30
                        )
                        st.session_state.wordcloud_keywords = keywords
                except Exception as e:
                    st.error(f"詞雲生成失敗：{e}")

        if st.session_state.get("wordcloud_img"):
            st.image(st.session_state.wordcloud_img, use_container_width=True)
        elif st.session_state.get("wordcloud_keywords"):
            st.markdown("**Top 30 關鍵字**：")
            kw_text = "  ·  ".join(
                f"**{w}** ({c})"
                for w, c in st.session_state.wordcloud_keywords
            )
            st.markdown(kw_text)


# ============ Tab 4: Settings (Redesigned Card Layout) ============
with tab_settings:
    st.markdown(
        '<div style="margin-bottom:1.2rem;">'
        '<h2 style="margin:0;">⚙️ 個人化設定</h2>'
        '<p style="color:#71717a;font-size:0.85rem;margin:0.2rem 0 0 0;">'
        'AI 會用呢啲資料為你公司專屬訂制摘要、識別 jargon、套用業界術語。</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.form("settings_form"):
        # === Card 1: 公司資料（左） + 預設選項（右）===
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown(
                '<div class="settings-card-title">🏢 公司資料</div>'
                '<div class="settings-card-desc">AI 會 reference 你嘅 employer</div>',
                unsafe_allow_html=True,
            )
            new_company = st.text_input(
                "公司名稱",
                value=user_settings.get("company_name", ""),
                placeholder="例：陳氏會計師樓",
                label_visibility="collapsed",
            )

            industry_keys = list(db.INDUSTRIES.keys())
            try:
                ind_idx = industry_keys.index(user_settings.get("industry", "generic"))
            except ValueError:
                ind_idx = 0
            new_industry = st.selectbox(
                "行業類型",
                options=industry_keys,
                format_func=lambda k: db.INDUSTRIES[k],
                index=ind_idx,
            )

        with col_right:
            st.markdown(
                '<div class="settings-card-title">📏 預設選項</div>'
                '<div class="settings-card-desc">新會議嘅 default 設定</div>',
                unsafe_allow_html=True,
            )
            length_keys = list(db.SUMMARY_LENGTHS.keys())
            try:
                len_idx = length_keys.index(user_settings.get("summary_length", "medium"))
            except ValueError:
                len_idx = 1
            new_length = st.selectbox(
                "預設摘要長度",
                options=length_keys,
                format_func=lambda k: db.SUMMARY_LENGTHS[k],
                index=len_idx,
            )
            # 預留位置畀將來其他 default option
            st.caption("💡 每次處理會議時都可以另揀")

        st.markdown("<div style='margin: 0.5rem 0;'></div>", unsafe_allow_html=True)

        # === Card 2: Jargon dictionary（full width）===
        st.markdown(
            '<div class="settings-card-title">📚 自定術語字典</div>'
            '<div class="settings-card-desc">'
            '加入你常用嘅客戶名、員工名、行業術語。AI 會特別留意呢啲詞，'
            '識別準確度大幅提升。'
            '</div>',
            unsafe_allow_html=True,
        )
        new_jargon = st.text_area(
            "Jargon",
            value=user_settings.get("jargon", ""),
            placeholder="例：HKFRS 18、Peter Chan、ABC Holdings、CFR、香港金管局、Cap. 622...",
            height=110,
            label_visibility="collapsed",
        )

        st.markdown("<div style='margin: 1rem 0;'></div>", unsafe_allow_html=True)

        # === Save button ===
        submitted = st.form_submit_button(
            "💾 儲存設定",
            type="primary",
            use_container_width=True,
        )
        if submitted:
            try:
                db.update_user_settings(
                    user["id"],
                    company_name=new_company.strip(),
                    industry=new_industry,
                    jargon=new_jargon.strip(),
                    summary_length=new_length,
                )
                st.success("✅ 設定已儲存！下次處理會議時生效。")
                st.rerun()
            except Exception as e:
                st.error(f"儲存失敗：{e}")

    # ============ 帳號資料 (separate card) ============
    st.markdown(
        '<div style="margin: 1.5rem 0 0.8rem 0;">'
        '<div class="settings-card-title">👤 帳號資料</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    info_col1, info_col2 = st.columns(2)
    with info_col1:
        st.text_input("Email", value=user["email"], disabled=True, key="acc_email")
    with info_col2:
        plan_display = {"free": "🆓 FREE", "pro": "⭐ PRO", "team": "👥 TEAM"}.get(plan, plan.upper())
        st.text_input("Plan", value=plan_display, disabled=True, key="acc_plan")

    st.markdown(
        f'<div style="margin-top:0.3rem;font-size:0.72rem;color:#a1a1aa;">'
        f'User ID: <code style="font-size:0.7rem;">{user["id"]}</code></div>',
        unsafe_allow_html=True,
    )
