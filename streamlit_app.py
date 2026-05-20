"""Minute.hk Cloud Web App - Streamlit + Supabase + Gemini + Stripe"""
import random
import threading
import time
import streamlit as st

import ai
import auth
import cloud_calendar
import cloud_exporters
# cloud_pptx imported lazily on button click (python-pptx may still be installing)
import cloud_stripe
import dashboard
import db


@st.cache_data(ttl=1800, show_spinner=False)  # 30 分鐘 cache
def get_cached_upgrade_url(user_id: str, email: str, plan: str = "pro") -> str | None:
    """生成 Stripe Checkout URL（cached）"""
    if not cloud_stripe.is_configured():
        return None
    try:
        return cloud_stripe.create_checkout_session(user_id, email, plan)
    except Exception:
        return None


def is_pro_user(user_plan: str) -> bool:
    """判斷係咪 Pro/Team 用戶（可以用 advanced features）"""
    return user_plan in ("pro", "team")


def show_pro_locked_toast(feature_name: str = "呢個功能"):
    """顯示 toast 提示用戶升級"""
    st.toast(f"🔒 {feature_name} 係 Pro 功能 — 撳上面 🆓 FREE 升級", icon="⭐")


def is_garbage_output(text: str) -> bool:
    """偵測 AI hallucinate 嘅 garbage（重複同一個字）"""
    import re
    from collections import Counter

    if not text or len(text) < 80:
        return False
    # Strip whitespace + markdown
    clean = re.sub(r"[\s\n#*\-|]+", "", text)
    if len(clean) < 80:
        return False
    # 如果單一字佔超過 40% → garbage
    most_common = Counter(clean).most_common(1)
    if not most_common:
        return False
    char, count = most_common[0]
    return (count / len(clean)) > 0.4


def show_friendly_error(e: Exception, context: str = "處理"):
    """Display user-friendly error for common Gemini issues"""
    err_msg = str(e)
    err_lower = err_msg.lower()

    if "503" in err_msg or "unavailable" in err_lower or "overload" in err_lower or "high demand" in err_lower:
        st.error(
            "⚠️ **Gemini AI 暫時擠塞**\n\n"
            "Google server 而家好多人用緊。我哋已經自動重試 3 次 + 試 fallback model。\n\n"
            "👉 **建議**：等 1-2 分鐘再試。"
        )
    elif "quota" in err_lower or "rate" in err_lower and "limit" in err_lower:
        st.error(
            "⚠️ **API quota 用完**\n\n"
            "免費 quota 每分鐘有上限。請等 30 秒再試。"
        )
    elif "429" in err_msg or "exceeded" in err_lower:
        st.error("⚠️ **太多 request**，請等 30 秒再試。")
    elif "401" in err_msg or "403" in err_msg or "authentication" in err_lower:
        st.error("⚠️ **API key 問題**，請聯絡 admin。")
    elif "\\x" in err_msg or err_msg.startswith("b'"):
        st.error("❌ 錄音處理失敗，請試吓另一個檔案。")
    else:
        if len(err_msg) > 300:
            err_msg = err_msg[:300] + "..."
        st.error(f"❌ {context}失敗：{err_msg}")


def _log_activity(label: str, status: str, duration: float = None, detail: str = ""):
    """Append entry to operation log (session_state).
    status: "running" | "done" | "error"
    """
    log = st.session_state.setdefault("activity_log", [])
    log.insert(0, {
        "time": time.strftime("%H:%M:%S"),
        "label": label,
        "status": status,
        "duration": duration,
        "detail": (detail or "")[:120],
    })
    # 只保留最近 20 條
    st.session_state["activity_log"] = log[:20]


def run_with_progress(func, *args, estimated_seconds: float = 30,
                       label: str = "處理中", activity_detail: str = "", **kwargs):
    """Run blocking func in thread + show animated % progress bar.

    Bar smoothly climbs to 95% based on elapsed/estimated, then 100% on completion.
    Gemini API 冇 real progress callback, 所以 % 係 fake-but-realistic estimation.

    Args:
        func: 要 run 嘅 function（例如 ai.process_audio）
        *args / **kwargs: 傳俾 func 嘅參數
        estimated_seconds: 估計需時 (用嚟 calibrate 進度)
        label: Progress bar 嘅文字

    Returns: func 嘅 return value
    Raises: func 拋出嘅 exception (re-raised on main thread)
    """
    # Streamlit thread context (令 thread 內可以讀 st.secrets)
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
        ctx = get_script_run_ctx()
    except Exception:
        ctx = None

    holder = {"result": None, "error": None, "done": False}

    def worker():
        try:
            holder["result"] = func(*args, **kwargs)
        except Exception as e:
            holder["error"] = e
        finally:
            holder["done"] = True

    thread = threading.Thread(target=worker, daemon=True)
    if ctx is not None:
        add_script_run_ctx(thread, ctx)
    thread.start()

    placeholder = st.empty()
    start = time.time()
    _start_unix = start  # for duration calc

    while not holder["done"]:
        elapsed = time.time() - start
        # Ease-out curve: 快爬到 70%, 慢慢爬到 95%, 永遠唔 hit 100% 直到 done
        ratio = elapsed / max(estimated_seconds, 1)
        if ratio <= 1.0:
            pct = ratio * 0.85  # 0 → 85% linearly during estimated time
        else:
            # 超時：85% → 95% asymptotically over additional time
            extra = ratio - 1.0
            pct = 0.85 + (0.95 - 0.85) * (1 - 0.5 ** extra)
        pct = min(0.95, pct)
        placeholder.progress(
            pct,
            text=f"{label} · {int(pct * 100)}% · 已用 {int(elapsed)}s（預計 {int(estimated_seconds)}s）",
        )
        time.sleep(0.4)

    placeholder.progress(1.0, text=f"✅ {label} · 100%")
    time.sleep(0.3)
    placeholder.empty()

    duration = time.time() - _start_unix
    if holder["error"]:
        _log_activity(label, "error", duration=duration,
                      detail=f"{activity_detail} · {str(holder['error'])[:80]}".strip(" ·"))
        raise holder["error"]
    _log_activity(label, "done", duration=duration, detail=activity_detail)
    return holder["result"]


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

# ============ Brand Logo (inline SVG, no external file needed) ============
LOGO_SVG = """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#06b6d4"/>
      <stop offset="100%" stop-color="#a855f7"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="100" height="100" rx="22" fill="url(#bgGrad)"/>
  <rect x="38" y="20" width="24" height="40" rx="12" fill="white"/>
  <circle cx="50" cy="32" r="2" fill="#06b6d4" opacity="0.5"/>
  <circle cx="50" cy="40" r="2" fill="#06b6d4" opacity="0.5"/>
  <circle cx="50" cy="48" r="2" fill="#06b6d4" opacity="0.5"/>
  <path d="M 24 50 Q 24 72 50 72 Q 76 72 76 50" stroke="white" stroke-width="5" fill="none" stroke-linecap="round"/>
  <line x1="50" y1="72" x2="50" y2="84" stroke="white" stroke-width="5" stroke-linecap="round"/>
</svg>"""

import base64
LOGO_B64 = base64.b64encode(LOGO_SVG.encode("utf-8")).decode("ascii")
LOGO_DATA_URI = f"data:image/svg+xml;base64,{LOGO_B64}"

# ============ Page Config ============
st.set_page_config(
    page_title="Minute.hk - 廣東話會議 AI",
    page_icon=LOGO_DATA_URI,
    layout="wide",
    initial_sidebar_state="collapsed",
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

    /* ============ Reduce fade during reruns / tab switch ============ */
    /* Streamlit 預設會 fade 緊個 page 等 user 知道 reload 緊
       我哋將 fade 變少 (opacity 0.5 → 0.9) 等 UX 更 snappy */
    .stApp [data-stale="true"] { opacity: 0.95 !important; }
    div[data-testid="stAppViewContainer"] [data-stale="true"] {
        opacity: 0.95 !important;
    }
    /* 隱藏右上角 running indicator (running man) */
    [data-testid="stStatusWidget"] { display: none !important; }
    /* Smooth transitions for tab content */
    [data-testid="stTabs"] [data-baseweb="tab-panel"] {
        animation: fadeIn 0.15s ease-out;
    }
    @keyframes fadeIn {
        from { opacity: 0.7; }
        to { opacity: 1; }
    }

    /* Misc tightening */
    div[data-testid="stForm"] { border: none; padding: 0; }
    [data-testid="stVerticalBlock"] { gap: 0.5rem !important; }
    .element-container { margin: 0 !important; padding: 0 !important; }

    /* ============ 📱 Mobile contrast fix - 強制深色字 ============ */
    /* 手機光線/小螢幕下，淺灰文字 (#71717a, #94a3b8 等) 對比唔夠，
       全部 force 黑色 / 深灰 */
    @media (max-width: 768px) {
        /* Body text 預設黑色 */
        .stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown li,
        .stMarkdown strong, .stMarkdown em, .stMarkdown div {
            color: #000 !important;
        }
        /* Caption / 小灰字 → 深灰 (仍可分到 hierarchy) */
        .stCaption, .stMarkdown small,
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p {
            color: #334155 !important;
        }
        /* Form labels - placeholder, label, select */
        .stTextInput label, .stSelectbox label, .stTextArea label,
        .stDateInput label, .stFileUploader label, .stRadio label {
            color: #000 !important;
            font-weight: 600 !important;
        }
        .stTextInput input, .stTextArea textarea, .stSelectbox div,
        .stDateInput input {
            color: #000 !important;
        }
        /* Placeholder - 用深啲灰 */
        .stTextInput input::placeholder, .stTextArea textarea::placeholder {
            color: #475569 !important;
            opacity: 1 !important;
        }
        /* Tabs - 未 selected 嘅都用深色 */
        .stTabs [data-baseweb="tab"] {
            color: #1e293b !important;
            font-weight: 600 !important;
        }
        /* Metric labels (Dashboard 用) */
        [data-testid="stMetricLabel"] {
            color: #1e293b !important;
            font-weight: 600 !important;
        }
        /* Expander titles (history meetings) */
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] details > summary {
            color: #000 !important;
            font-weight: 600 !important;
        }
        /* H5 (uppercase headings) - 由灰色 #71717a 改深灰 */
        h5 { color: #334155 !important; }
        /* Top bar email + usage 細字 */
        [data-testid="stApp"] div[style*="color:#475569"],
        [data-testid="stApp"] div[style*="color:#64748b"],
        [data-testid="stApp"] div[style*="color:#94a3b8"] {
            color: #1e293b !important;
        }
        /* Inline HTML 黑色 override - 任何 span/div with light gray inline color */
        span[style*="#71717a"], span[style*="#94a3b8"], span[style*="#64748b"],
        div[style*="color:#71717a"], div[style*="color:#94a3b8"],
        p[style*="color:#94a3b8"] {
            color: #1e293b !important;
        }
    }

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

    /* Main content max-width (sidebar 已 remove, 用返 wider layout) */
    .main .block-container { max-width: 1100px; }

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

    /* Upgrade button in user bar */
    .upgrade-btn {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 8px;
        background: linear-gradient(135deg, #06b6d4 0%, #a855f7 100%);
        color: white !important;
        font-size: 0.75rem;
        font-weight: 600;
        text-decoration: none !important;
        box-shadow: 0 2px 8px rgba(6, 182, 212, 0.3);
        transition: transform 0.15s, box-shadow 0.15s;
    }
    .upgrade-btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(6, 182, 212, 0.45);
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
    # Center the login card with side columns (desktop: ~33% width, mobile: full)
    _auth_l, auth_col, _auth_r = st.columns([1, 2, 1])
    with auth_col:
        st.markdown(
            f"""
            <div style='text-align:center;margin:0.5rem 0 0.8rem 0;'>
                <img src='{LOGO_DATA_URI}' alt='Minute.hk' style='width:48px;height:48px;'/>
                <h2 style='margin:0.4rem 0 0 0;font-size:1.4rem;'>
                    Minute<span style='color:#06b6d4;'>.hk</span>
                </h2>
                <p style='color:#64748b;margin:0.2rem 0 0 0;font-size:0.82rem;'>
                    廣東話會議 AI 摘要 · 香港人專用
                </p>
            </div>
            """,
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
                            # 如果有 pending invite code (signup 後要 verify email 嗰陣 stored)，
                            # 喺登入成功之後即刻 claim
                            pending = st.session_state.pop("_pending_invite_code", None)
                            pending_plan = st.session_state.pop("_pending_invite_plan", "pro")
                            if pending:
                                u = auth.get_user()
                                if u:
                                    ok2, info = db.claim_invite_code_and_upgrade(
                                        pending, u["id"], pending_plan
                                    )
                                    if ok2:
                                        st.success(f"🎉 邀請碼已啟用 - 你而家係 {info.upper()} 用戶")
                                    else:
                                        st.warning(f"⚠️ 邀請碼啟用失敗：{info}")
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

        with tab_signup:
            # Init captcha (一次性 per session)
            if "captcha_a" not in st.session_state:
                _new_captcha()

            st.caption("🎟️ Beta 測試中 - 需要邀請碼註冊")
            with st.form("signup_form"):
                email = st.text_input("Email", placeholder="you@example.com",
                                      key="su_email", label_visibility="collapsed")
                password = st.text_input("Password", type="password", placeholder="密碼（至少 6 位）",
                                         key="su_pass", label_visibility="collapsed")
                password2 = st.text_input("Confirm", type="password", placeholder="確認密碼",
                                          key="su_pass2", label_visibility="collapsed")
                invite_code = st.text_input(
                    "邀請碼",
                    placeholder="🎟️ 邀請碼（測試期免費升 Pro）",
                    key="su_invite",
                    label_visibility="collapsed",
                )
                # 🤖 Math captcha 防 bot - 題目用 caption 永遠顯示 (唔淨係 placeholder)
                a = st.session_state.captcha_a
                b = st.session_state.captcha_b
                op = st.session_state.captcha_op
                st.markdown(
                    f"<div style='font-size:0.85rem;color:#475569;margin-top:0.5rem;"
                    f"padding:0.4rem 0.6rem;background:#f1f5f9;border-radius:6px;"
                    f"border-left:3px solid #06b6d4;'>"
                    f"🤖 防 bot 驗證：請計 <strong>{a} {op} {b} = ?</strong>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                captcha_ans = st.text_input(
                    "驗證碼",
                    placeholder="輸入答案",
                    key="captcha_input",
                    label_visibility="collapsed",
                )
                submit = st.form_submit_button("✨ 用邀請碼註冊", type="primary", use_container_width=True)
                if submit:
                    if not email or not password:
                        st.error("請填 email 同密碼")
                    elif password != password2:
                        st.error("兩次密碼唔同")
                    elif not _check_captcha(captcha_ans):
                        st.error(f"驗證碼錯誤。{a} {op} {b} = ?")
                        _new_captcha()  # regen 防 bot brute force
                    else:
                        # Validate invite code BEFORE signup (read-only check)
                        code_ok, code_info = db.validate_invite_code(invite_code)
                        if not code_ok:
                            st.error(f"🎟️ {code_info}")
                            # 不 regen captcha - 用戶只係填錯邀請碼，唔好為難佢
                        else:
                            target_plan = code_info  # "pro" / "team" / etc
                            ok, msg = auth.signup(email, password)
                            if ok:
                                new_user = auth.get_user()
                                if new_user:
                                    # Auto-login path - claim immediately
                                    ok2, info = db.claim_invite_code_and_upgrade(
                                        invite_code, new_user["id"], target_plan
                                    )
                                    if ok2:
                                        st.success(f"🎉 註冊成功！邀請碼已啟用 - 你而家係 {info.upper()} 用戶")
                                    else:
                                        st.warning(f"註冊咗，但邀請碼啟用失敗：{info}")
                                    _new_captcha()  # success - regen for safety
                                    st.rerun()
                                else:
                                    # Email confirmation 開咗 - 唔可以即刻 claim
                                    st.session_state["_pending_invite_code"] = invite_code.strip()
                                    st.session_state["_pending_invite_plan"] = target_plan
                                    st.success(
                                        msg + "\n\n"
                                        "✅ 邀請碼已 reserved，"
                                        f"verify email 之後喺呢個 browser 登入即升 {target_plan.upper()}。"
                                    )
                                    _new_captcha()  # success - regen
                            else:
                                st.error(msg)
                                # 不 regen captcha - signup 失敗（例如 email 已註冊）唔好為難用戶

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
            "&nbsp;·&nbsp;免費版 100 分鐘/月</p>",
            unsafe_allow_html=True,
        )

    st.stop()

# ============ Logged in - Main App ============
user = auth.get_user()
plan = db.get_user_plan(user["id"])
plan_emoji = {"free": "🆓", "pro": "⭐", "team": "👥"}.get(plan, "🆓")

# === Compute usage for top bar ===
monthly_used = db.get_monthly_usage_seconds(user["id"]) / 60
daily_used = db.get_daily_usage_seconds(user["id"]) / 60
if plan == "free":
    monthly_limit_str = f"{db.FREE_MONTHLY_SECONDS / 60:.0f}"
    daily_limit_str = f"{db.FREE_DAILY_SECONDS / 60:.0f}"
else:
    monthly_limit_str = f"{db.PRO_MONTHLY_SECONDS / 60:.0f}"
    daily_limit_str = f"{db.PRO_DAILY_SECONDS / 60:.0f}"

# === Top User Bar (主畫面上方) ===
# 用 columns 分左右，左邊 HTML logo+usage，右邊用 popover badge
ubar_outer = st.container()
with ubar_outer:
    st.markdown(
        '<div style="background:white;border:1px solid #e2e8f0;border-radius:10px;'
        'padding:0.4rem 1rem;margin-bottom:0.6rem;box-shadow:0 1px 2px rgba(0,0,0,0.03);">',
        unsafe_allow_html=True,
    )
    col_left, col_mid, col_log, col_right, col_menu = st.columns([4, 2.4, 0.7, 1.6, 0.9])

    with col_left:
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:10px;padding-top:6px;">
            <img src="{LOGO_DATA_URI}" alt="Minute.hk" style="width:32px;height:32px;flex-shrink:0;"/>
            <div>
                <div style="font-size:1rem;font-weight:700;color:#18181b;line-height:1.2;">
                    Minute<span style="color:#06b6d4;">.hk</span>
                </div>
                <div style="font-size:0.72rem;color:#64748b;line-height:1.2;">
                    📊 今日 <strong>{daily_used:.1f}/{daily_limit_str}</strong>分
                    · 本月 <strong>{monthly_used:.1f}/{monthly_limit_str}</strong>分
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_mid:
        st.markdown(
            f'<div style="text-align:right;padding-top:10px;font-size:0.82rem;color:#475569;">'
            f'👋 {user["email"]}</div>',
            unsafe_allow_html=True,
        )

    with col_log:
        _alog = st.session_state.get("activity_log", [])
        _badge = f" ({len(_alog)})" if _alog else ""
        with st.popover(f"📋{_badge}", use_container_width=True, help="操作記錄"):
            st.markdown("##### 📋 最近操作")
            if not _alog:
                st.caption("仲未做過任何 AI 操作")
            else:
                _status_emoji = {"running": "🟢", "done": "✅", "error": "❌"}
                for entry in _alog:
                    em = _status_emoji.get(entry["status"], "•")
                    dur = entry.get("duration")
                    dur_txt = f" · **{dur:.1f}s**" if dur else ""
                    detail = entry.get("detail") or ""
                    st.markdown(
                        f"<div style='padding:4px 0;border-bottom:1px solid #f1f5f9;font-size:0.82rem;'>"
                        f"{em} <span style='color:#64748b;'>{entry['time']}</span> "
                        f"{entry['label']}{dur_txt}"
                        + (f"<br><span style='color:#94a3b8;font-size:0.74rem;padding-left:1.4rem;'>{detail}</span>" if detail else "")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                if st.button("🗑️ 清空", key="clear_activity_log", use_container_width=True):
                    st.session_state.pop("activity_log", None)
                    st.rerun()

    with col_right:
        if plan == "free":
            # 🆓 FREE badge 變 popover button - click 彈出升級
            with st.popover(f"🆓 FREE", use_container_width=True):
                st.markdown("##### ⭐ 升級 Pro")
                st.markdown(
                    '<div style="font-size:1.4rem;font-weight:800;color:#06b6d4;'
                    'margin:0.2rem 0;">HKD 15 <span style="font-size:0.85rem;'
                    'font-weight:500;color:#71717a;">/月</span></div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    "**用量**  \n"
                    "✓ 200 分鐘/月（Free: 100）  \n"
                    "✓ 30 分鐘/日（Free: 15）  \n\n"
                    "**進階 AI**  \n"
                    "✓ 🎭 語氣分析  \n"
                    "✓ 🌐 6 國語言翻譯（Free: 英/簡中）  \n"
                    "✓ 📊 PPT 生成 + PDF 匯出  \n"
                    "✓ 🔗 繼續會議（AI 合併）  \n\n"
                    "**整合**  \n"
                    "✓ 📅 Google Calendar / Outlook 一鍵 add  \n"
                    "✓ 🗂️ Industry-specific prompts  \n"
                    "✓ 🏷️ 自定 jargon dictionary  \n"
                    "✓ 📈 Dashboard + 詞雲  \n"
                    "✓ 🔍 過往會議搜尋 + date filter  \n"
                    "✓ 📧 Email 支援"
                )

                # ⚙️ Detailed Stripe status check (debug 用)
                if not cloud_stripe.STRIPE_AVAILABLE:
                    st.warning(
                        "⚠️ Stripe SDK 仲未 install\n\n"
                        "Streamlit Cloud 仲喺 rebuild。等 5-10 分鐘 hard refresh 再試。"
                    )
                elif not st.secrets.get("STRIPE_SECRET_KEY"):
                    st.warning(
                        "⚠️ `STRIPE_SECRET_KEY` 未喺 Streamlit secrets\n\n"
                        "去 share.streamlit.io → 你個 app → Settings → Secrets 加上去。"
                    )
                elif not st.secrets.get("STRIPE_PRICE_ID_PRO"):
                    st.warning(
                        "⚠️ `STRIPE_PRICE_ID_PRO` 未設定\n\n"
                        "去 Stripe Dashboard 攞你 HKD 15 嘅 Price ID（price_xxx...），"
                        "貼入 Streamlit secrets。"
                    )
                else:
                    # Stripe URL 只 generate 一次，cache 喺 session（避免每次 popover 開都 call API）
                    cache_key = f"_stripe_url_{user['id']}"
                    err_key = f"_stripe_err_{user['id']}"

                    if cache_key not in st.session_state and err_key not in st.session_state:
                        try:
                            st.session_state[cache_key] = cloud_stripe.create_checkout_session(
                                user["id"], user["email"], "pro"
                            )
                        except Exception as e:
                            st.session_state[err_key] = str(e)

                    if st.session_state.get(cache_key):
                        st.link_button(
                            "⭐ 立即升級", st.session_state[cache_key],
                            type="primary", use_container_width=True,
                        )
                        st.caption("撳完跳轉 Stripe Checkout · 自動 sync plan (webhook)")
                    elif st.session_state.get(err_key):
                        st.error(f"⚠️ Stripe 錯誤：{st.session_state[err_key][:200]}")
        else:
            badge_color = {"pro": "#047857", "team": "#92400e"}.get(plan, "#1e66f5")
            badge_bg = {"pro": "#ecfdf5", "team": "#fef3c7"}.get(plan, "#eff6ff")
            st.markdown(
                f'<div style="text-align:right;padding-top:10px;">'
                f'<span style="display:inline-block;padding:4px 12px;'
                f'border-radius:8px;background:{badge_bg};color:{badge_color};'
                f'font-weight:700;font-size:0.78rem;">'
                f'{plan_emoji} {plan.upper()}</span></div>',
                unsafe_allow_html=True,
            )

    with col_menu:
        with st.popover("⋯", use_container_width=True, help="Menu"):
            st.markdown(
                "<a href='https://minutehk.vercel.app' target='_blank' "
                "style='color:#1e66f5;text-decoration:none;display:block;padding:6px 0;'>"
                "🏠 主頁</a>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<a href='https://minutehk.vercel.app/#faq' target='_blank' "
                "style='color:#1e66f5;text-decoration:none;display:block;padding:6px 0;'>"
                "❓ 常見問題</a>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<a href='mailto:xavierchow61@gmail.com' "
                "style='color:#1e66f5;text-decoration:none;display:block;padding:6px 0;'>"
                "📧 聯絡支援</a>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<hr style='margin:0.4rem 0;border:none;border-top:1px solid #e2e8f0;'>",
                unsafe_allow_html=True,
            )
            if st.button("🚪 登出", use_container_width=True, key="logout_menu"):
                auth.logout()
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# Load user settings (used by 新會議 + 設定 tab)
user_settings = db.get_user_settings(user["id"])

# Pro user check (used throughout)
IS_PRO = is_pro_user(plan)

# Main content tabs
tab_new, tab_history, tab_dashboard, tab_settings = st.tabs([
    "🎙️ 新會議", "📚 過往會議", "📊 Dashboard", "⚙️ 設定"
])

# ============ Tab 1: New Meeting ============
with tab_new:
    # 同 History tab 嘅 [3,1,1] 一致風格 - 客戶/項目大 input + 細 selector
    col1, col2, col3 = st.columns([3, 3, 1])
    with col1:
        client_name = st.text_input("客戶", placeholder="ABC Limited",
                                    label_visibility="collapsed")
    with col2:
        project_name = st.text_input("項目", placeholder="2026 audit",
                                     label_visibility="collapsed")
    with col3:
        # 紀要長度 selector — Pro 至可揀，Free 強制 medium
        if IS_PRO:
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
        else:
            summary_length = "medium"
            st.selectbox(
                "長度",
                options=["🔒 中（Pro）"],
                index=0,
                disabled=True,
                label_visibility="collapsed",
                key="meeting_length_free",
                help="⭐ Pro 用戶可揀短/中/長",
            )

    # 處理模式：完整摘要 vs 純轉文字
    process_mode = st.radio(
        "處理模式",
        options=["📝 完整摘要 + AI 分析", "📋 純轉文字（快速 · 唔做分析）"],
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        key="process_mode",
        help="純轉文字：只 transcribe 錄音內容，唔做總結 / action items / 分析",
    )
    transcribe_only_mode = process_mode.startswith("📋")

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
            btn_label = "📋 開始純轉文字" if transcribe_only_mode else "🚀 開始 AI 處理"
            if st.button(btn_label, type="primary", use_container_width=True):
                try:
                    mime_type = uploaded.type or "audio/mpeg"
                    audio_bytes = uploaded.read()

                    if transcribe_only_mode:
                        # === 純轉文字 mode (快約 50% - 唔做 summary) ===
                        estimated = max(10, int(file_size_mb * 8))
                        tr_result = run_with_progress(
                            ai.transcribe_only,
                            audio_bytes=audio_bytes,
                            mime_type=mime_type,
                            estimated_seconds=estimated,
                            label="📋 轉文字",
                        )
                        transcript_text = tr_result["transcript"]

                        # 包裝成 markdown 顯示（前綴 header 標明係純轉文字）
                        summary_md = (
                            "# 📋 純文字稿\n\n"
                            f"**錄音**：{uploaded.name} · "
                            f"**模式**：純轉文字（無分析）\n\n"
                            "---\n\n"
                            f"{transcript_text}"
                        )

                        with st.status("✅ 轉文字完成 - 儲存中...", expanded=False) as status:
                            if is_garbage_output(transcript_text):
                                st.warning(
                                    "⚠️ **錄音質量問題** - AI 輸出重複字符。"
                                    "請確保麥克風正常 + 安靜環境重錄。"
                                )
                                status.update(label="⚠️ 質量問題", state="error")
                                st.stop()
                            saved = db.save_meeting(
                                user_id=user["id"],
                                summary=summary_md,
                                transcript=transcript_text,
                                client=client_name or None,
                                project=project_name or None,
                                duration_seconds=est_duration_sec,
                                audio_filename=uploaded.name,
                            )
                            if saved and saved.get("id"):
                                st.session_state.current_meeting_id = saved["id"]
                            status.update(label="✅ 完成！", state="complete")

                        st.session_state.last_summary = summary_md
                        st.session_state.last_meeting_name = client_name or "純轉文字"
                        st.session_state.pop("last_translation", None)
                        st.session_state.pop("last_translation_lang", None)
                        st.session_state.pop("last_sentiment", None)
                        st.session_state.pop("pptx_main", None)
                        st.session_state.pop("edit_main_mode", None)
                        st.session_state.pop("edit_main_buffer", None)

                    else:
                        # === 完整摘要 + AI 分析 mode ===
                        estimated = max(15, int(file_size_mb * 12))
                        result = run_with_progress(
                            ai.process_audio,
                            audio_bytes=audio_bytes,
                            mime_type=mime_type,
                            client_name=client_name,
                            project_name=project_name,
                            industry=user_settings.get("industry", "generic"),
                            length=summary_length,
                            custom_jargon=user_settings.get("jargon", ""),
                            company_name=user_settings.get("company_name", ""),
                            estimated_seconds=estimated,
                            label="🤖 AI 處理音頻",
                        )

                        with st.status("✅ AI 完成 - 儲存中...", expanded=False) as status:
                            if is_garbage_output(result["summary"]):
                                st.warning(
                                    "⚠️ **偵測到錄音質量問題**\n\n"
                                    "AI 嘅輸出係重複字符（譬如「喂喂喂...」），通常代表：\n"
                                    "- 麥克風收唔到聲音\n"
                                    "- 背景噪音太大 / 講者聲音太細\n"
                                    "- 錄音太短\n\n"
                                    "**呢次冇 save 落資料庫**。請：\n"
                                    "1. 確保麥克風正常\n"
                                    "2. 安靜環境重新錄音\n"
                                    "3. 至少錄 15 秒，講大聲清楚"
                                )
                                status.update(label="⚠️ 質量問題", state="error")
                                st.stop()

                            saved = db.save_meeting(
                                user_id=user["id"],
                                summary=result["summary"],
                                client=client_name or None,
                                project=project_name or None,
                                duration_seconds=est_duration_sec,
                                audio_filename=uploaded.name,
                            )
                            if saved and saved.get("id"):
                                st.session_state.current_meeting_id = saved["id"]
                            status.update(label="✅ 完成！", state="complete")

                            st.session_state.last_summary = result["summary"]
                            st.session_state.last_meeting_name = client_name or "會議"
                            st.session_state.pop("last_translation", None)
                            st.session_state.pop("last_translation_lang", None)
                            st.session_state.pop("last_sentiment", None)
                            st.session_state.pop("pptx_main", None)
                            st.session_state.pop("edit_main_mode", None)
                            st.session_state.pop("edit_main_buffer", None)

                except Exception as e:
                    show_friendly_error(e, "AI 處理")
                    with st.expander("🔍 技術詳情"):
                        st.exception(e)

    # 顯示最後一次嘅 summary - 用 @st.fragment 等 edit/save 只 rerun 呢一 block
    @st.fragment
    def _render_summary_edit_main():
        if not st.session_state.get("last_summary"):
            return

        st.divider()

        header_col, edit_col = st.columns([5, 1])
        with header_col:
            st.markdown("#### 📝 會議紀要")
        with edit_col:
            if st.session_state.get("edit_main_mode"):
                if st.button("❌ 取消", key="cancel_edit_main", use_container_width=True):
                    st.session_state.pop("edit_main_mode", None)
                    st.session_state.pop("edit_main_buffer", None)
                    st.rerun(scope="fragment")
            else:
                if st.button("✏️ 編輯", key="edit_main_btn", use_container_width=True):
                    st.session_state.edit_main_mode = True
                    st.session_state.edit_main_buffer = st.session_state.last_summary
                    st.rerun(scope="fragment")

        if st.session_state.get("edit_main_mode"):
            edited = st.text_area(
                "編輯紀要（Markdown）",
                value=st.session_state.edit_main_buffer,
                height=400,
                label_visibility="collapsed",
                key="edit_main_textarea",
            )
            save_col, _ = st.columns([1, 4])
            with save_col:
                if st.button("💾 儲存修改", type="primary",
                             use_container_width=True, key="save_edit_main"):
                    if st.session_state.get("current_meeting_id"):
                        try:
                            db.update_meeting_summary(
                                meeting_id=st.session_state.current_meeting_id,
                                user_id=user["id"],
                                new_summary=edited,
                                additional_duration=0,
                            )
                        except Exception as e:
                            st.error(f"DB update 失敗：{e}")
                    st.session_state.last_summary = edited
                    st.session_state.pop("edit_main_mode", None)
                    st.session_state.pop("edit_main_buffer", None)
                    st.session_state.pop("last_translation", None)
                    st.session_state.pop("last_sentiment", None)
                    st.session_state.pop("pptx_main", None)
                    st.toast("✅ 紀要已更新", icon="✏️")
                    st.rerun(scope="fragment")
        else:
            st.markdown(st.session_state.last_summary)

    _render_summary_edit_main()

    if st.session_state.get("last_summary"):

        st.markdown("##### 📥 下載")
        col_md, col_word, col_pdf, col_ppt, col_ics = st.columns(5)
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
            if IS_PRO:
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
            else:
                if st.button("🔒 PDF", use_container_width=True, key="pdf_locked_main",
                             help="⭐ 升級 Pro 解鎖 PDF 匯出"):
                    show_pro_locked_toast("PDF 匯出")

        with col_ppt:
            if IS_PRO:
                if st.button("📊 PPT", use_container_width=True, key="ppt_main"):
                    st.session_state._gen_pptx_main = True
                    st.toast("📊 AI 生成 PPT 中... (約 10-20 秒)", icon="🤖")
            else:
                if st.button("🔒 PPT", use_container_width=True, key="ppt_locked_main",
                             help="⭐ 升級 Pro 解鎖 PPT 生成"):
                    show_pro_locked_toast("PPT 生成")

        with col_ics:
            if st.button("📅 加 Calendar", use_container_width=True, key="ics_main"):
                st.session_state._gen_ics_main = True
                st.toast("📅 AI 抽取 action items 中... (約 5-10 秒)", icon="🤖")

        # ============ Process AFTER columns（避免 duplicate row）============
        # PPT 生成
        if st.session_state.pop("_gen_pptx_main", False):
            try:
                import cloud_pptx
                pptx_bytes = run_with_progress(
                    cloud_pptx.summary_to_pptx_bytes, st.session_state.last_summary,
                    estimated_seconds=15,
                    label="📊 AI 結構化 + 生成 PPT",
                )
                st.session_state.pptx_main = pptx_bytes
                st.toast("✅ PPT 已生成 - 撳下面 download", icon="📊")
            except ImportError:
                st.error("⚠️ Streamlit Cloud 仲喺度裝 python-pptx (5-10 分鐘)。")
            except Exception as e:
                st.error(f"❌ PPT 失敗：{e}")
                with st.expander("🔍 技術詳情"):
                    st.exception(e)

        if st.session_state.get("pptx_main"):
            st.download_button(
                "📥 下載 PPT (.pptx)",
                st.session_state.pptx_main,
                file_name=f"{base_name}_簡報.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                key="dl_pptx_main",
                use_container_width=True,
            )

        # Calendar 抽 action items
        if st.session_state.pop("_gen_ics_main", False):
            try:
                items = run_with_progress(
                    ai.extract_action_items, st.session_state.last_summary,
                    estimated_seconds=10,
                    label="📅 AI 抽取 action items",
                )
                if not items:
                    st.warning("呢個 meeting 冇可以加入 calendar 嘅事項")
                else:
                    st.session_state.cal_items_main = items
                    st.session_state.ics_main = cloud_calendar.action_items_to_ics(
                        items,
                        meeting_title=base_name,
                        client=st.session_state.get("last_meeting_name", ""),
                    )
                    st.toast(f"✅ 揾到 {len(items)} 個 action items", icon="📅")
            except Exception as e:
                show_friendly_error(e, "Action items 抽取")

        # 顯示 calendar 選項（per action item）
        if st.session_state.get("cal_items_main"):
            items = st.session_state.cal_items_main
            client_for_cal = st.session_state.get("last_meeting_name", "")
            with st.expander(f"📅 {len(items)} 個 action items - 加入 Calendar", expanded=True):
                for i, it in enumerate(items):
                    task = it.get("task") or "（無描述）"
                    deadline = it.get("deadline") or "未定"
                    assignee = it.get("assignee") or "—"
                    priority = it.get("priority", "medium")
                    p_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "")

                    g_url = cloud_calendar.google_calendar_url(it, client=client_for_cal, meeting_title=base_name)
                    o_url = cloud_calendar.outlook_calendar_url(it, client=client_for_cal, meeting_title=base_name)

                    st.markdown(
                        f"**{p_emoji} {task}**  \n"
                        f"<span style='color:#71717a;font-size:0.8rem;'>"
                        f"👤 {assignee} · 📅 {deadline}</span>",
                        unsafe_allow_html=True,
                    )
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if IS_PRO:
                            st.link_button("🟦 Google Calendar", g_url, use_container_width=True)
                        else:
                            if st.button("🔒 Google Calendar", use_container_width=True,
                                         key=f"g_locked_{i}", help="⭐ Pro 功能"):
                                show_pro_locked_toast("Google Calendar 一鍵 add")
                    with btn_col2:
                        if IS_PRO:
                            st.link_button("🟪 Outlook", o_url, use_container_width=True)
                        else:
                            if st.button("🔒 Outlook", use_container_width=True,
                                         key=f"o_locked_{i}", help="⭐ Pro 功能"):
                                show_pro_locked_toast("Outlook 一鍵 add")
                    st.markdown("<hr style='margin:0.5rem 0; opacity:0.3;'>", unsafe_allow_html=True)

                # 整體 ICS download
                if st.session_state.get("ics_main"):
                    st.download_button(
                        "📥 一次過下載 .ics（其他 calendar app）",
                        st.session_state.ics_main,
                        file_name=f"{base_name}_calendar.ics",
                        mime="text/calendar",
                        key="dl_ics_main",
                        use_container_width=True,
                    )

        # === 🌐 翻譯 + 🎭 語氣分析 ===
        st.markdown("##### 🤖 AI 進階分析")

        col_t, col_s = st.columns(2)

        # --- Translate (Free: English + 簡中 only; Pro: all 6) ---
        with col_t:
            if IS_PRO:
                translate_options = list(ai.TRANSLATE_TARGETS.values())
            else:
                # Free user 只可揀 English + Simplified Chinese
                translate_options = ["English", "简体中文"]
            target_label = st.selectbox(
                "🌐 翻譯紀要",
                options=translate_options,
                key="translate_target",
                label_visibility="collapsed",
                help="⭐ Pro 用戶可揀 6 國語言" if not IS_PRO else None,
            )
            if st.button("🌐 翻譯", use_container_width=True, key="btn_translate"):
                target_code = next(
                    (k for k, v in ai.TRANSLATE_TARGETS.items() if v == target_label),
                    "en"
                )
                try:
                    translated = run_with_progress(
                        ai.translate, st.session_state.last_summary, target_code,
                        estimated_seconds=10,
                        label=f"🌐 翻譯成 {target_label}",
                    )
                    st.session_state.last_translation = translated
                    st.session_state.last_translation_lang = target_label
                except Exception as e:
                    st.error(f"翻譯失敗：{e}")

        # --- Sentiment (Pro only) ---
        with col_s:
            st.markdown(
                "<div style='height:38px;display:flex;align-items:center;color:#64748b;font-size:0.85rem;'>"
                "🎭 分析會議語氣 + 風險信號"
                "</div>",
                unsafe_allow_html=True,
            )
            if IS_PRO:
                if st.button("🎭 語氣分析", use_container_width=True, key="btn_sentiment"):
                    try:
                        sentiment = run_with_progress(
                            ai.analyze_sentiment, st.session_state.last_summary,
                            estimated_seconds=10,
                            label="🎭 AI 分析語氣 + 風險",
                        )
                        st.session_state.last_sentiment = sentiment
                    except Exception as e:
                        st.error(f"分析失敗：{e}")
            else:
                if st.button("🔒 語氣分析", use_container_width=True, key="btn_sentiment_locked",
                             help="⭐ 升級 Pro 解鎖"):
                    show_pro_locked_toast("語氣分析")

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
        # 每個 meeting 包成獨立 fragment - 撳 button 唔會 reload 其他 meeting
        @st.fragment
        def _render_meeting(m):
            date = m["created_at"][:16].replace("T", " ")
            client = m.get("client") or "—"
            project = m.get("project") or "—"
            duration_min = (m.get("duration_seconds") or 0) / 60

            # 顯示時 highlight match
            title = f"📅 {date} · {client} / {project} · {duration_min:.1f} 分鐘"

            with st.expander(title):
                # m 已經由 list_meetings 帶埋 summary，唔需要再 fetch (省 50 個 query/rerun)
                full = m
                if full:
                    edit_key = f"h_edit_mode_{m['id']}"
                    buf_key = f"h_edit_buf_{m['id']}"

                    # Edit toggle header
                    h_head_col, h_edit_col = st.columns([5, 1])
                    with h_head_col:
                        st.markdown(f"**📝 {client or 'Meeting'} 紀要**")
                    with h_edit_col:
                        if st.session_state.get(edit_key):
                            if st.button("❌ 取消", key=f"h_cancel_{m['id']}",
                                         use_container_width=True):
                                st.session_state.pop(edit_key, None)
                                st.session_state.pop(buf_key, None)
                                st.rerun(scope="fragment")
                        else:
                            if st.button("✏️ 編輯", key=f"h_edit_btn_{m['id']}",
                                         use_container_width=True):
                                st.session_state[edit_key] = True
                                st.session_state[buf_key] = full["summary"]
                                st.rerun(scope="fragment")

                    if st.session_state.get(edit_key):
                        # 編輯模式
                        edited = st.text_area(
                            "編輯紀要",
                            value=st.session_state[buf_key],
                            height=350,
                            label_visibility="collapsed",
                            key=f"h_edit_ta_{m['id']}",
                        )
                        save_col, _ = st.columns([1, 3])
                        with save_col:
                            if st.button("💾 儲存", type="primary",
                                         use_container_width=True,
                                         key=f"h_save_{m['id']}"):
                                try:
                                    db.update_meeting_summary(
                                        meeting_id=m["id"],
                                        user_id=user["id"],
                                        new_summary=edited,
                                        additional_duration=0,
                                    )
                                    # In-place update m["summary"] 令 fragment rerun 就有新值，
                                    # 唔需要 full page rerun
                                    m["summary"] = edited
                                    st.session_state.pop(edit_key, None)
                                    st.session_state.pop(buf_key, None)
                                    # Clear cached generated content
                                    for k in [f"h_tr_{m['id']}", f"h_sent_{m['id']}",
                                              f"h_pptx_{m['id']}", f"h_ics_{m['id']}"]:
                                        st.session_state.pop(k, None)
                                    st.toast("✅ 紀要已更新", icon="✏️")
                                    st.rerun(scope="fragment")
                                except Exception as e:
                                    st.error(f"儲存失敗：{e}")
                    else:
                        st.markdown(full["summary"])

                    # 4-column download row (mobile-safe: avoids auto-wrap)
                    col_md, col_word, col_pdf, col_ppt = st.columns(4)
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
                        if IS_PRO:
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
                        else:
                            if st.button("🔒 PDF", key=f"pdf_lk_{m['id']}",
                                         use_container_width=True, help="⭐ Pro 功能"):
                                show_pro_locked_toast("PDF 匯出")
                    with col_ppt:
                        if IS_PRO:
                            if st.button("📊 PPT", key=f"ppt_btn_{m['id']}",
                                         use_container_width=True):
                                st.session_state[f"_h_gen_pptx_{m['id']}"] = True
                                st.toast("📊 PPT 生成中... (10-20s)", icon="🤖")
                        else:
                            if st.button("🔒 PPT", key=f"ppt_lk_{m['id']}",
                                         use_container_width=True, help="⭐ Pro 功能"):
                                show_pro_locked_toast("PPT 生成")

                    # 刪除 button - 獨立一行，避免誤撳 + mobile wrap
                    _, col_del = st.columns([3, 1])
                    with col_del:
                        if st.button("🗑️ 刪除", key=f"del_{m['id']}", use_container_width=True):
                            db.delete_meeting(m["id"], user["id"])
                            st.rerun()

                    # PPT generation (after all columns - avoid duplicate row)
                    if st.session_state.pop(f"_h_gen_pptx_{m['id']}", False):
                        try:
                            import cloud_pptx
                            pptx_bytes = run_with_progress(
                                cloud_pptx.summary_to_pptx_bytes, full["summary"],
                                estimated_seconds=15,
                                label="📊 AI 生成 PPT",
                            )
                            st.session_state[f"h_pptx_{m['id']}"] = pptx_bytes
                            st.toast("✅ PPT 已生成", icon="📊")
                        except ImportError:
                            st.error("python-pptx 仲安裝中，請等 5 分鐘")
                        except Exception as e:
                            st.error(f"❌ {e}")

                    # PPT download button
                    if st.session_state.get(f"h_pptx_{m['id']}"):
                        st.download_button(
                            "📥 下載 PPT (.pptx)",
                            st.session_state[f"h_pptx_{m['id']}"],
                            file_name=f"{base_name}_簡報.pptx",
                            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            key=f"h_dl_pptx_{m['id']}",
                            use_container_width=True,
                        )

                    # === 🤖 AI 進階分析（每個 meeting）===
                    st.markdown("**🤖 AI 進階分析**")
                    h_col_t, h_col_s = st.columns(2)

                    # --- Translate (Free: 2 languages; Pro: all 6) ---
                    with h_col_t:
                        if IS_PRO:
                            h_tr_options = list(ai.TRANSLATE_TARGETS.values())
                        else:
                            h_tr_options = ["English", "简体中文"]
                        target_label = st.selectbox(
                            "翻譯為",
                            options=h_tr_options,
                            key=f"h_tr_target_{m['id']}",
                            label_visibility="collapsed",
                            help="⭐ Pro 用戶可揀 6 國語言" if not IS_PRO else None,
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
                            try:
                                translated = run_with_progress(
                                    ai.translate, full["summary"], target_code,
                                    estimated_seconds=10,
                                    label=f"🌐 翻譯成 {target_label}",
                                )
                                st.session_state[f"h_tr_{m['id']}"] = translated
                                st.session_state[f"h_tr_lang_{m['id']}"] = target_label
                            except Exception as e:
                                st.error(f"翻譯失敗：{e}")

                    # --- Sentiment (Pro only) ---
                    with h_col_s:
                        st.markdown(
                            "<div style='height:38px;display:flex;align-items:center;"
                            "color:#64748b;font-size:0.82rem;'>"
                            "🎭 分析會議語氣 + 風險"
                            "</div>",
                            unsafe_allow_html=True,
                        )
                        if IS_PRO:
                            if st.button(
                                "🎭 語氣分析",
                                key=f"h_btn_sent_{m['id']}",
                                use_container_width=True,
                            ):
                                try:
                                    sent = run_with_progress(
                                        ai.analyze_sentiment, full["summary"],
                                        estimated_seconds=10,
                                        label="🎭 AI 分析語氣 + 風險",
                                    )
                                    st.session_state[f"h_sent_{m['id']}"] = sent
                                except Exception as e:
                                    st.error(f"分析失敗：{e}")
                        else:
                            if st.button(
                                "🔒 語氣分析",
                                key=f"h_btn_sent_lk_{m['id']}",
                                use_container_width=True,
                                help="⭐ Pro 功能",
                            ):
                                show_pro_locked_toast("語氣分析")

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
                            try:
                                items = run_with_progress(
                                    ai.extract_action_items, full["summary"],
                                    estimated_seconds=10,
                                    label="📅 AI 抽取 action items",
                                )
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
                        if IS_PRO:
                            if st.button(
                                "🔗 繼續呢個會議",
                                key=f"h_btn_cont_{m['id']}",
                                use_container_width=True,
                            ):
                                st.session_state[f"h_cont_open_{m['id']}"] = True
                        else:
                            if st.button(
                                "🔒 繼續會議",
                                key=f"h_btn_cont_lk_{m['id']}",
                                use_container_width=True,
                                help="⭐ Pro 功能",
                            ):
                                show_pro_locked_toast("繼續會議")

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

        # Call fragment for each meeting - 每個 button 撳只 rerun 對應 meeting
        for m in meetings:
            _render_meeting(m)


# ============ Tab 3: Dashboard ============
with tab_dashboard:
  @st.fragment
  def _render_dashboard_tab():
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

        # === Monthly trend (Pro only) ===
        st.markdown("##### 📈 每月會議數量")
        if not IS_PRO:
            st.info(
                "🔒 **每月趨勢圖** 係 Pro 功能。"
                "撳上面 🆓 FREE badge 升級解鎖。"
            )
        elif stats["monthly_counts"] and len(stats["monthly_counts"]) > 1:
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

        # === Word Cloud (Pro only) ===
        st.markdown("---")
        st.markdown("##### ☁️ 詞雲 (Top Keywords)")
        if not IS_PRO:
            st.info(
                "🔒 **詞雲分析** 係 Pro 功能。"
                "撳上面 🆓 FREE badge 升級解鎖。"
            )
        elif st.button("🔄 生成詞雲", key="gen_wordcloud"):
            with st.spinner("分析所有會議文字..."):
                try:
                    # Lazy fetch summaries (only when clicked)
                    summaries_text = db.get_summaries_for_wordcloud(user["id"])
                    img_bytes = dashboard.generate_wordcloud_image(
                        summaries_text, max_words=80
                    )
                    if img_bytes:
                        st.session_state.wordcloud_img = img_bytes
                    else:
                        keywords = dashboard.extract_keywords(summaries_text, top_n=30)
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

  _render_dashboard_tab()


# ============ Tab 4: Settings (Redesigned Card Layout) ============
with tab_settings:
  @st.fragment
  def _render_settings_tab():
    st.markdown(
        '<div style="margin-bottom:1.2rem;">'
        '<h2 style="margin:0;">⚙️ 個人化設定</h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.form("settings_form"):
        # === Row 1: 公司名稱 + 行業類型（並排）===
        col_a, col_b = st.columns(2)

        with col_a:
            new_company = st.text_input(
                "🏢 公司名稱",
                value=user_settings.get("company_name", ""),
                placeholder="例：陳氏會計師樓",
            )

        with col_b:
            if IS_PRO:
                industry_keys = list(db.INDUSTRIES.keys())
                try:
                    ind_idx = industry_keys.index(user_settings.get("industry", "generic"))
                except ValueError:
                    ind_idx = 0
                new_industry = st.selectbox(
                    "🎯 行業類型",
                    options=industry_keys,
                    format_func=lambda k: db.INDUSTRIES[k],
                    index=ind_idx,
                )
            else:
                new_industry = "generic"
                st.selectbox(
                    "🔒 行業類型 (Pro)",
                    options=["🏢 一般商務"],
                    index=0,
                    disabled=True,
                    help="⭐ Pro 用戶可揀會計/法律/醫療/銷售等",
                )

        # === Row 2: 預設摘要長度（Pro 至可揀）===
        if IS_PRO:
            length_keys = list(db.SUMMARY_LENGTHS.keys())
            try:
                len_idx = length_keys.index(user_settings.get("summary_length", "medium"))
            except ValueError:
                len_idx = 1
            new_length = st.selectbox(
                "📏 預設摘要長度",
                options=length_keys,
                format_func=lambda k: db.SUMMARY_LENGTHS[k],
                index=len_idx,
                help="新會議嘅 default。每次處理時都可以另揀。",
            )
        else:
            new_length = "medium"
            st.selectbox(
                "🔒 預設摘要長度 (Pro)",
                options=["中（標準格式）"],
                index=0,
                disabled=True,
                help="⭐ Pro 用戶可揀短/中/長",
            )

        # === Row 3: Jargon (Pro 至 enable) ===
        if IS_PRO:
            new_jargon = st.text_area(
                "📚 自定術語字典 (jargon / 人名 / 客戶名)",
                value=user_settings.get("jargon", ""),
                placeholder="例：HKFRS 18、Peter Chan、ABC Holdings、CFR、香港金管局、Cap. 622...",
                height=100,
                help="用逗號或新行分隔。AI 會特別留意呢啲詞，識別準確度大幅提升。",
            )
        else:
            new_jargon = ""
            st.text_area(
                "🔒 自定術語字典 (Pro)",
                value="",
                placeholder="⭐ 升級 Pro 解鎖 — 加入你公司專屬 jargon、客戶名、人名",
                height=100,
                disabled=True,
                help="⭐ Pro 用戶可加 jargon dictionary 大幅提升 AI 識別準確度",
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
                st.rerun(scope="fragment")
            except Exception as e:
                st.error(f"儲存失敗：{e}")

    # 帳號資料 section 隱藏 — Email + Plan 已喺 top user bar 顯示

  _render_settings_tab()
