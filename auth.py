"""Supabase Auth for Streamlit"""
import streamlit as st
from supabase import Client, create_client


def get_supabase() -> Client:
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_ANON_KEY"],
    )


def init_session():
    """Init session state for auth"""
    if "user" not in st.session_state:
        st.session_state.user = None
    if "session" not in st.session_state:
        st.session_state.session = None


def get_user() -> dict | None:
    """Return current logged-in user dict, or None"""
    init_session()
    return st.session_state.user


def is_logged_in() -> bool:
    return get_user() is not None


def signup(email: str, password: str) -> tuple[bool, str]:
    """
    Returns (success, message)
    """
    if len(password) < 6:
        return False, "密碼至少 6 位"
    try:
        sb = get_supabase()
        result = sb.auth.sign_up({"email": email, "password": password})
        if result.user:
            return True, "✅ 註冊成功！請到 email 確認啟用 account，然後登入。"
        return False, "註冊失敗，請再試。"
    except Exception as e:
        msg = str(e)
        if "already registered" in msg.lower() or "User already" in msg:
            return False, "呢個 email 已註冊，請直接登入。"
        return False, f"註冊失敗：{e}"


def login(email: str, password: str) -> tuple[bool, str]:
    try:
        sb = get_supabase()
        result = sb.auth.sign_in_with_password({"email": email, "password": password})
        if result.user:
            st.session_state.user = {
                "id": result.user.id,
                "email": result.user.email,
            }
            st.session_state.session = result.session
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
    try:
        sb = get_supabase()
        sb.auth.sign_out()
    except Exception:
        pass
    st.session_state.user = None
    st.session_state.session = None


def reset_password(email: str) -> tuple[bool, str]:
    try:
        sb = get_supabase()
        sb.auth.reset_password_for_email(email)
        return True, "✅ 重設密碼 link 已 send 去你 email"
    except Exception as e:
        return False, f"失敗：{e}"
