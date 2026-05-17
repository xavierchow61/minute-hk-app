"""Minute.hk Cloud Web App - Streamlit + Supabase + Gemini"""
import streamlit as st

import ai
import auth
import db

# ============ Page Config ============
st.set_page_config(
    page_title="Minute.hk - 廣東話會議 AI",
    page_icon="🎙️",
    layout="wide",
    menu_items={
        "About": "Minute.hk - 香港人專用 AI 會議摘要工具",
    },
)

# ============ Style ============
st.markdown("""
<style>
    .stApp { max-width: 1100px; margin: 0 auto; }
    .stButton button { border-radius: 8px; }
    h1 { color: #1e293b; }
    .stAlert { border-radius: 12px; }
    div[data-testid="stToolbar"] { display: none; }
    footer { display: none; }
    #MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

auth.init_session()

# ============ Auth UI (if not logged in) ============
if not auth.is_logged_in():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🎙️ Minute.hk")
        st.caption("廣東話會議 AI 摘要 · 香港人專用")
        st.write("")

        tab_login, tab_signup, tab_reset = st.tabs(["🔓 登入", "✨ 註冊", "🔑 忘記密碼"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email", placeholder="you@example.com")
                password = st.text_input("密碼", type="password")
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
            with st.form("signup_form"):
                email = st.text_input("Email", placeholder="you@example.com", key="su_email")
                password = st.text_input("密碼（至少 6 位）", type="password", key="su_pass")
                password2 = st.text_input("確認密碼", type="password", key="su_pass2")
                st.caption("註冊即同意使用條款及私隱政策")
                submit = st.form_submit_button("✨ 免費註冊", type="primary", use_container_width=True)
                if submit:
                    if not email or not password:
                        st.error("請填 email 同密碼")
                    elif password != password2:
                        st.error("兩次密碼唔同")
                    else:
                        ok, msg = auth.signup(email, password)
                        if ok:
                            st.success(msg)
                            st.info("📧 請開你個 email mailbox，撳啟用 link。然後返呢度登入。")
                        else:
                            st.error(msg)

        with tab_reset:
            with st.form("reset_form"):
                email = st.text_input("Email", key="rp_email")
                submit = st.form_submit_button("📧 send reset link", use_container_width=True)
                if submit and email:
                    ok, msg = auth.reset_password(email)
                    (st.success if ok else st.error)(msg)

        st.write("")
        st.caption("⬅️ [返主頁](https://minutehk.vercel.app)")

    st.stop()

# ============ Logged in - Main App ============
user = auth.get_user()

# Sidebar
with st.sidebar:
    st.markdown(f"### 👋 Hi!")
    st.markdown(f"`{user['email']}`")

    plan = db.get_user_plan(user["id"])
    plan_emoji = {"free": "🆓", "pro": "⭐", "team": "👥"}.get(plan, "🆓")
    st.markdown(f"**Plan**: {plan_emoji} {plan.upper()}")

    if plan == "free":
        used_sec = db.get_monthly_usage_seconds(user["id"])
        used_min = used_sec / 60
        limit_min = db.FREE_MONTHLY_SECONDS / 60
        progress = min(used_sec / db.FREE_MONTHLY_SECONDS, 1.0)
        st.progress(progress, text=f"今月已用 {used_min:.1f}/{limit_min:.0f} 分鐘")
        if progress >= 0.8:
            st.warning("快用完啦！考慮升級 Pro")
            st.link_button("⭐ 升級 Pro", "https://minutehk.vercel.app/#pricing",
                           use_container_width=True)

    st.write("---")
    if st.button("🚪 登出", use_container_width=True):
        auth.logout()
        st.rerun()

    st.write("---")
    st.caption("[← 返主頁](https://minutehk.vercel.app)")

# Main content
tab_new, tab_history = st.tabs(["🎙️ 新會議", "📚 過往會議"])

# ============ Tab 1: New Meeting ============
with tab_new:
    st.title("🎙️ 處理新會議")

    col1, col2 = st.columns(2)
    with col1:
        client_name = st.text_input("客戶（optional）", placeholder="ABC Limited")
    with col2:
        project_name = st.text_input("項目（optional）", placeholder="2026 年度 audit")

    uploaded = st.file_uploader(
        "📁 上傳會議錄音",
        type=["mp3", "m4a", "wav", "mp4", "ogg", "flac", "webm"],
        help="支援 mp3/m4a/wav/mp4/ogg/flac/webm，最大 200MB",
    )

    if uploaded:
        file_size_mb = uploaded.size / (1024 * 1024)
        st.caption(f"📄 `{uploaded.name}` ({file_size_mb:.1f} MB)")
        st.audio(uploaded)

        # Estimate duration (rough: 1MB ≈ 60 sec for mp3 128kbps)
        est_duration_sec = file_size_mb * 60

        # Check quota
        can_process_now, msg = db.can_process(user["id"], est_duration_sec)
        if not can_process_now:
            st.error(msg)
            st.link_button("⭐ 升級 Pro 無限用", "https://minutehk.vercel.app/#pricing")
        else:
            if st.button("🚀 開始 AI 處理", type="primary", use_container_width=True):
                with st.status("🤖 AI 處理中（可能要 30 秒到 2 分鐘）...", expanded=True) as status:
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

                        st.success(f"🎉 紀要已生成！Meeting ID: `{saved.get('id', '?')[:8]}`")

                        # Display summary
                        st.markdown("---")
                        st.markdown(result["summary"])

                        # Download buttons
                        col1, col2 = st.columns(2)
                        with col1:
                            st.download_button(
                                "📥 下載 Markdown",
                                result["summary"],
                                file_name=f"{client_name or 'meeting'}_紀要.md",
                                mime="text/markdown",
                                use_container_width=True,
                            )

                    except Exception as e:
                        st.error(f"❌ 處理失敗：{e}")

# ============ Tab 2: History ============
with tab_history:
    st.title("📚 過往會議")

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
                # Load full meeting on demand
                full = db.get_meeting(m["id"], user["id"])
                if full:
                    st.markdown(full["summary"])
                    col1, col2 = st.columns([1, 5])
                    with col1:
                        if st.button("🗑️ 刪除", key=f"del_{m['id']}"):
                            db.delete_meeting(m["id"], user["id"])
                            st.rerun()
