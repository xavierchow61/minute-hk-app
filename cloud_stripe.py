"""Stripe Checkout + Customer Portal integration"""
import streamlit as st

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False


def _get_stripe():
    """Initialize Stripe with secret key from secrets"""
    if not STRIPE_AVAILABLE:
        raise RuntimeError("Stripe SDK 未安裝")
    api_key = st.secrets.get("STRIPE_SECRET_KEY", "")
    if not api_key:
        raise RuntimeError("未設定 STRIPE_SECRET_KEY")
    stripe.api_key = api_key
    return stripe


def is_configured() -> bool:
    """Check if Stripe is configured"""
    return STRIPE_AVAILABLE and bool(st.secrets.get("STRIPE_SECRET_KEY"))


# Stripe Price IDs（喺 Stripe Dashboard 整完之後填）
PRICE_IDS = {
    "pro": "STRIPE_PRICE_ID_PRO",     # secrets.toml key
    "team": "STRIPE_PRICE_ID_TEAM",
}


def create_checkout_session(user_id: str, user_email: str,
                             plan: str = "pro") -> str:
    """
    建立 Stripe Checkout Session，返回 redirect URL。
    plan = 'pro' 或 'team'
    """
    s = _get_stripe()

    price_id = st.secrets.get(PRICE_IDS[plan])
    if not price_id:
        raise RuntimeError(f"未設定 {PRICE_IDS[plan]} （喺 Streamlit secrets 加）")

    app_url = st.secrets.get("APP_URL", "https://minute-hk-app.streamlit.app")

    session = s.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        customer_email=user_email,
        client_reference_id=user_id,  # 用 user_id 去 webhook 識別 user
        success_url=f"{app_url}?upgrade=success",
        cancel_url=f"{app_url}?upgrade=cancel",
        allow_promotion_codes=True,
        metadata={
            "user_id": user_id,
            "plan": plan,
        },
        subscription_data={
            "metadata": {
                "user_id": user_id,
                "plan": plan,
            },
        },
    )
    return session.url


def create_portal_session(stripe_customer_id: str) -> str:
    """
    建立 Stripe Customer Portal session（俾用戶 cancel / 改 plan / 睇 invoice）
    """
    s = _get_stripe()
    app_url = st.secrets.get("APP_URL", "https://minute-hk-app.streamlit.app")
    portal = s.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=app_url,
    )
    return portal.url


def get_pricing_info() -> dict:
    """Returns pricing display info（俾 UI 用）"""
    return {
        "free": {
            "name": "免費",
            "price": "HKD 0",
            "period": "/月",
            "features": [
                "30 分鐘錄音/月",
                "廣東話 + 中英夾雜",
                "基本會議紀要",
                "Word + PDF 下載",
            ],
        },
        "pro": {
            "name": "個人 Pro",
            "price": "HKD 99",
            "period": "/月",
            "highlight": "⭐ 最受歡迎",
            "features": [
                "✨ 無限錄音",
                "全部進階功能",
                "優先處理",
                "Email support",
                "RAG AI 問答（即將）",
                "翻譯 + 情緒分析（即將）",
            ],
        },
        "team": {
            "name": "團隊",
            "price": "HKD 599",
            "period": "/月",
            "features": [
                "5 用戶帳號",
                "共享 client 資料庫",
                "Admin dashboard",
                "Priority support",
            ],
        },
    }
