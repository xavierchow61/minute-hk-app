"""Supabase Auth for Streamlit"""
import streamlit as st
from supabase import Client, create_client

# Disposable email domains - 防 bot 用 temp email 開咗一大堆 account
# Source: https://github.com/disposable-email-domains/disposable-email-domains (subset)
DISPOSABLE_DOMAINS = {
    "10minutemail.com", "10minutemail.net", "20minutemail.com",
    "anonymbox.com", "bccto.me", "bigprofessor.so", "binkmail.com",
    "burnermail.io", "byom.de", "cuvox.de", "deadaddress.com",
    "deadspam.com", "discardmail.com", "disposable.email",
    "disposableinbox.com", "dispostable.com", "dontreg.com",
    "easytrashmail.com", "emailondeck.com", "emailtemporanea.com",
    "etranquil.com", "fakeinbox.com", "fakemailgenerator.com",
    "fakemail.fr", "fakeinformation.com", "filzmail.com",
    "freemail.ms", "getnada.com", "ghosttexter.de",
    "goemailgo.com", "guerrillamail.com", "guerrillamail.de",
    "guerrillamail.net", "guerrillamail.org", "guerrillamailblock.com",
    "harakirimail.com", "hidemail.de", "hidzz.com",
    "incognitomail.com", "incognitomail.org", "inboxalias.com",
    "jetable.org", "junkemailfilter.com", "klzlk.com",
    "kurzepost.de", "mail-temp.com", "mail-temporaire.fr",
    "mail-tester.com", "mailcatch.com", "maildrop.cc",
    "maildx.com", "mailexpire.com", "mailforspam.com",
    "mailimate.com", "mailinator.com", "mailinator.net",
    "mailinator.org", "mailinator2.com", "mailme.lv",
    "mailmetrash.com", "mailnesia.com", "mailnull.com",
    "mailtrash.net", "mintemail.com", "moakt.com",
    "mt2014.com", "mt2015.com", "mytrashmail.com",
    "neverbox.com", "no-spam.ws", "nobulk.com",
    "noclickemail.com", "notmailinator.com", "nowmymail.com",
    "objectmail.com", "obobbo.com", "odaymail.com",
    "onewaymail.com", "owlpic.com", "pookmail.com",
    "rcpt.at", "recode.me", "rmqkr.net",
    "rppkn.com", "sharklasers.com", "shieldedmail.com",
    "shieldemail.com", "shortmail.net", "sneakemail.com",
    "snkmail.com", "spambox.us", "spamfree24.org",
    "spamgourmet.com", "spamspot.com", "tempemail.com",
    "tempemail.net", "tempemailaddress.com", "tempinbox.co.uk",
    "tempinbox.com", "tempmail.com", "tempmail.email",
    "tempmail.net", "tempmail2.com", "tempmaildemand.com",
    "tempmailer.com", "tempmailer.de", "tempomail.fr",
    "temporaryemail.net", "temporaryemail.us", "temporaryforwarding.com",
    "throwam.com", "throwaway.email", "throwawayemailaddresses.com",
    "throwawaymail.com", "trashinbox.com", "trashmail.at",
    "trashmail.com", "trashmail.de", "trashmail.io",
    "trashmail.me", "trashmail.net", "trashmail.org",
    "trashmailer.com", "trashymail.com", "tyldd.com",
    "vidchart.com", "wegwerfadresse.de", "wegwerfemail.de",
    "wetrainbayarea.org", "wronghead.com", "yopmail.com",
    "yopmail.fr", "yopmail.net", "zehnminutenmail.de",
    "0clickemail.com", "1secmail.com", "30minutemail.com",
    "5ymail.com",
}


def is_disposable_email(email: str) -> bool:
    domain = email.lower().rsplit("@", 1)[-1].strip()
    return domain in DISPOSABLE_DOMAINS


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
    if "@" not in email:
        return False, "Email 格式錯誤"
    if is_disposable_email(email):
        return False, "唔接受 disposable / temp email，請用真實 email"
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


def reset_password(email: str, redirect_url: str | None = None) -> tuple[bool, str]:
    """Send reset password email. redirect_url 需要 whitelist 喺 Supabase
    Auth → URL Configuration → Redirect URLs。

    Email 入面條 link click 之後 Supabase 會 redirect 返 {redirect_url}?code=xxx，
    我哋自動 append type=recovery 等 app 識別到呢個 flow。
    """
    try:
        sb = get_supabase()
        if redirect_url:
            sep = "&" if "?" in redirect_url else "?"
            full_redirect = f"{redirect_url}{sep}type=recovery"
            sb.auth.reset_password_for_email(
                email, options={"redirect_to": full_redirect}
            )
        else:
            sb.auth.reset_password_for_email(email)
        return True, (
            "✅ 重設密碼 link 已 send 去你 email。"
            "請喺 1 小時內 click 條 link 設定新密碼。"
        )
    except Exception as e:
        return False, f"失敗：{e}"


def update_password(new_password: str) -> tuple[bool, str]:
    """更新當前 logged-in user 嘅密碼。要求現時有 active session
    （recovery session 都 OK — exchange_recovery_code 之後）。
    """
    if len(new_password) < 6:
        return False, "密碼至少 6 位"
    try:
        sb = get_supabase()
        sb.auth.update_user({"password": new_password})
        return True, "✅ 密碼已更新！請用新密碼登入。"
    except Exception as e:
        return False, f"更新密碼失敗：{e}"


def exchange_recovery_code(code: str) -> tuple[bool, str]:
    """用 password recovery URL 嘅 code (PKCE flow) 換 session.

    成功 = user 而家有臨時 session，可以 call update_password()。
    """
    try:
        sb = get_supabase()
        result = sb.auth.exchange_code_for_session({"auth_code": code})
        if result and result.session and result.user:
            st.session_state.user = {
                "id": result.user.id,
                "email": result.user.email,
            }
            st.session_state.session = result.session
            st.session_state._session_attached = True
            return True, result.user.email
        return False, "Link 無效或已被使用"
    except Exception as e:
        msg = str(e).lower()
        if "expired" in msg or "invalid" in msg:
            return False, "Link 已過期或無效，請重新申請"
        return False, f"處理失敗：{e}"


def set_recovery_session(access_token: str, refresh_token: str) -> tuple[bool, str]:
    """用 password recovery URL 嘅 access_token (implicit flow) 建立 session.

    Supabase email 條 link click 完，default implicit flow 會 redirect 去
    {app}?type=recovery#access_token=xxx&refresh_token=yyy
    要 JS shim 將 hash 轉成 query，然後呢度 set_session.
    """
    try:
        sb = get_supabase()
        result = sb.auth.set_session(access_token, refresh_token or "")
        if result and result.user:
            st.session_state.user = {
                "id": result.user.id,
                "email": result.user.email,
            }
            st.session_state.session = result.session
            st.session_state._session_attached = True
            return True, result.user.email
        return False, "Session 建立失敗"
    except Exception as e:
        msg = str(e).lower()
        if "expired" in msg or "invalid" in msg:
            return False, "Link 已過期或無效，請重新申請"
        return False, f"處理失敗：{e}"
