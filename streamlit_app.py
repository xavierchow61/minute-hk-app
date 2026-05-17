"""Minute.hk Cloud Web App - Streamlit + Supabase + Gemini + Stripe"""
import random
import streamlit as st

import ai
import auth
import cloud_exporters
import cloud_stripe
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

# ============ Style - professional + compact ============
st.markdown("""
<style>
    /* Layout */
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 800px;
    }
    .stApp { background: #fafbfc; }

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

    /* Misc */
    .stAlert { border-radius: 10px; font-size: 0.9rem; }
    div[data-testid="stToolbar"] { display: none; }
    footer { display: none; }
    #MainMenu { visibility: hidden; }
    div[data-testid="stTabs"] { margin-top: 0.3rem; }
    div[data-testid="stForm"] { border: none; padding: 0; }

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

    /* Custom header bar */
    .app-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.5rem 0 1rem 0;
        border-bottom: 1px solid #f1f5f9;
        margin-bottom: 1rem;
    }
    .app-logo {
        font-size: 1.2rem;
        font-weight: 700;
        color: #1e293b;
    }
    .app-logo span { color: #1e66f5; }
    .app-plan {
        font-size: 0.75rem;
        padding: 3px 10px;
        border-radius: 12px;
        background: #eff6ff;
        color: #1e66f5;
        font-weight: 600;
    }
    .app-plan.pro { background: #ecfdf5; color: #047857; }
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

# Custom header bar
plan_class = "pro" if plan in ("pro", "team") else ""
plan_emoji = {"free": "🆓", "pro": "⭐", "team": "👥"}.get(plan, "🆓")
st.markdown(f"""
<div class="app-header">
    <div class="app-logo">🎙️ Minute<span>.hk</span></div>
    <div class="app-plan {plan_class}">{plan_emoji} {plan.upper()}</div>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    # === Logo ===
    st.markdown(
        "<div style='font-size:1.1rem;font-weight:700;color:#1e293b;padding:0 0 0.8rem 0;'>"
        "🎙️ Minute<span style='color:#1e66f5;'>.hk</span></div>",
        unsafe_allow_html=True,
    )

    # === User card ===
    plan_badge_class = {"free": "badge-free", "pro": "badge-pro", "team": "badge-team"}.get(plan, "badge-free")
    st.markdown(f"""
    <div class="sidebar-user-card">
        <div class="sidebar-user-name">👋 Hi!</div>
        <div class="sidebar-user-email">{user["email"]}</div>
        <span class="sidebar-plan-badge {plan_badge_class}">{plan_emoji} {plan.upper()}</span>
    </div>
    """, unsafe_allow_html=True)

    # === Usage stats ===
    st.markdown("##### 📊 用量")
    if plan == "free":
        # Monthly
        monthly_used = db.get_monthly_usage_seconds(user["id"]) / 60
        monthly_limit = db.FREE_MONTHLY_SECONDS / 60
        monthly_progress = min(monthly_used / monthly_limit, 1.0)
        st.caption(f"本月：{monthly_used:.1f} / {monthly_limit:.0f} 分鐘")
        st.progress(monthly_progress)

        # Daily
        daily_used = db.get_daily_usage_seconds(user["id"]) / 60
        daily_limit = db.FREE_DAILY_SECONDS / 60
        daily_progress = min(daily_used / daily_limit, 1.0)
        st.caption(f"今日：{daily_used:.1f} / {daily_limit:.0f} 分鐘")
        st.progress(daily_progress)
    else:
        monthly_used = db.get_monthly_usage_seconds(user["id"]) / 60
        st.caption(f"本月：{monthly_used:.1f} 分鐘（無限）")
        daily_used = db.get_daily_usage_seconds(user["id"]) / 60
        daily_limit = db.PRO_DAILY_SECONDS / 60
        daily_progress = min(daily_used / daily_limit, 1.0)
        st.caption(f"今日：{daily_used:.1f} / {daily_limit:.0f} 分鐘")
        st.progress(daily_progress)

    # === Upgrade Pro (only if free) ===
    if plan == "free":
        st.markdown("##### ⭐ 升級 Pro")
        st.caption("無限錄音 · 全部功能 · HKD 99/月")
        if cloud_stripe.is_configured():
            if st.button("立即升級", type="primary", use_container_width=True):
                with st.spinner("跳轉去 Stripe..."):
                    try:
                        url = cloud_stripe.create_checkout_session(
                            user_id=user["id"],
                            user_email=user["email"],
                            plan="pro",
                        )
                        st.markdown(
                            f'<meta http-equiv="refresh" content="0;url={url}">',
                            unsafe_allow_html=True,
                        )
                        st.link_button("👉 撳呢度繼續", url, use_container_width=True)
                    except Exception as e:
                        st.error(f"無法跳轉：{e}")
        else:
            st.caption("⚠️ Stripe 未設定")

    # === Quick links ===
    st.markdown("##### 🔗 快速連結")
    st.markdown(
        "<a href='https://minutehk.vercel.app' target='_blank' "
        "style='color:#1e66f5;text-decoration:none;font-size:0.85rem;'>"
        "🏠 主頁</a>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<a href='https://minutehk.vercel.app/#faq' target='_blank' "
        "style='color:#1e66f5;text-decoration:none;font-size:0.85rem;'>"
        "❓ 常見問題</a>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<a href='mailto:xavierchow61@gmail.com' "
        "style='color:#1e66f5;text-decoration:none;font-size:0.85rem;'>"
        "📧 聯絡支援</a>",
        unsafe_allow_html=True,
    )

    # === Logout (bottom) ===
    st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
    if st.button("🚪 登出", use_container_width=True):
        auth.logout()
        st.rerun()

# Main content tabs
tab_new, tab_history = st.tabs(["🎙️ 新會議", "📚 過往會議"])

# ============ Tab 1: New Meeting ============
with tab_new:
    st.markdown("### 處理新會議")

    col1, col2 = st.columns(2)
    with col1:
        client_name = st.text_input("客戶", placeholder="ABC Limited", label_visibility="visible")
    with col2:
        project_name = st.text_input("項目", placeholder="2026 audit", label_visibility="visible")

    uploaded = st.file_uploader(
        "上傳會議錄音",
        type=["mp3", "m4a", "wav", "mp4", "ogg", "flac", "webm"],
        help="支援 mp3/m4a/wav/mp4/ogg/flac/webm，最大 200MB",
        label_visibility="collapsed",
    )

    if uploaded:
        file_size_mb = uploaded.size / (1024 * 1024)
        st.caption(f"📄 `{uploaded.name}` · {file_size_mb:.1f} MB")
        st.audio(uploaded)

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

                    except Exception as e:
                        err_msg = str(e)
                        if "\\x" in err_msg or err_msg.startswith("b'"):
                            err_msg = "錄音處理失敗，請試吓另一個檔案。"
                        elif len(err_msg) > 300:
                            err_msg = err_msg[:300] + "..."
                        st.error(f"❌ {err_msg}")
                        with st.expander("🔍 技術詳情"):
                            st.exception(e)

    # 顯示最後一次嘅 summary + download buttons
    if st.session_state.get("last_summary"):
        st.divider()
        st.markdown("#### 📝 會議紀要")
        st.markdown(st.session_state.last_summary)

        st.markdown("##### 📥 下載")
        col_md, col_word, col_pdf = st.columns(3)
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

# ============ Tab 2: History ============
with tab_history:
    st.markdown("### 過往會議")

    meetings = db.list_meetings(user["id"], limit=50)
    if not meetings:
        st.info("仲未有任何會議紀錄。上面 tab 上傳第一個錄音啦！")
    else:
        st.caption(f"共 {len(meetings)} 個 meeting")
        for m in meetings:
            date = m["created_at"][:16].replace("T", " ")
            client = m.get("client") or "—"
            project = m.get("project") or "—"
            duration_min = (m.get("duration_seconds") or 0) / 60

            with st.expander(f"📅 {date} · {client} / {project} · {duration_min:.1f} 分鐘"):
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
