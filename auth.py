"""Supabase Auth for Streamlit"""
import streamlit as st
from supabase import Client, create_client


def get_supabase() -> Client:
    """
    Returns ONE shared Supabase client per Streamlit session.
    呢個好重要 — 唔可以每次 create 新 client，否則 auth session 會 lose，
    RLS policy 會 fail (auth.uid() 變 NULL).
    """
    if "supabase_client" not in st.session_state:
        st.session_state.supabase_client = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_ANON_KEY"],
        )
    sb = st.session_state.supabase_client

    # 每次 rerun 都重新 attach session（Streamlit 嘅 session_state 唔會 persist client 內部嘅 auth）
    session = st.session_state.get("session")
    if session and not st.session_state.get("_session_attached"):
        try:
            sb.auth.set_session(session.access_token, session.refresh_token)
            st.session_state._session_attached = True
        except Exception:
            pass

    return sb


def init_session():
    """Init session state for auth"""
    if "user" not in st.session_state:
        st.session_state.user = None
    if "session" not in st.session_state:
        st.session_state.session = None
    if "_session_attached" not in st.session_state:
        st.session_state._session_attached = False


def get_user() -> dict | None:
    init_session()
    return st.session_state.user


def is_logged_in() -> bool:
    return get_user() is not None


def signup(email: str, password: str) -> tuple[bool, str]:
    if len(password) < 6:
        return False, "密碼至少 6 位"
    try:
        sb = get_supabase()
        result = sb.auth.sign_up({"email": email, "password": password})
        if result.user:
            # 如果 email confirmation 已 disable，session 會直接俾我哋 → auto-login
            if result.session:
                st.session_state.user = {
                    "id": result.user.id,
                    "email": result.user.email,
                }
                st.session_state.session = result.session
                st.session_state._session_attached = True
                return True, "✅ 註冊成功！正在登入..."
            return True, "✅ 註冊成功！請到 email 確認啟用，然後登入。"
        return False, "註冊失敗，請再試。"
    except Exception as e:
        msg = str(e)
        if "already" in msg.lower() or "registered" in msg.lower():
            return False, "呢個 email 已註冊，請直接登入。"
        return False, f"註冊失敗：{e}"


def login(email: str, password: str) -> tuple[bool, str]:
    try:
        sb = get_supabase()
        result = sb.auth.sign_in_with_password({"email": email, "password": password})
        if result.user and result.session:
            st.session_state.user = {
                "id": result.user.id,
                "email": result.user.email,
            }
            st.session_state.session = result.session
            st.session_state._session_attached = True   # client 已自動 attached
            return True, "✅ 登入成功"
        return False, "登入失敗"
    except Exception as e:
        msg = str(e).lower()
        if "invalid" in msg or "credentials" in msg:
            return False, "Email 或密碼錯誤"
        if "confirmed" in msg or "confirm" in msg:
            return False, "請先到 email 確認啟用 account"
        return False, f"登入失敗：{e}"


def logout():
    sb = st.session_state.get("supabase_client")
    if sb:
        try:
            sb.auth.sign_out()
        except Exception:
            pass
    st.session_state.user = None
    st.session_state.session = None
    st.session_state._session_attached = False


def reset_password(email: str) -> tuple[bool, str]:
    try:
        sb = get_supabase()
        sb.auth.reset_password_for_email(email)
        return True, "✅ 重設密碼 link 已 send 去你 email"
    except Exception as e:
        return False, f"失敗：{e}"
