"""Supabase DB queries for meetings + usage tracking (cached)"""
from datetime import date, datetime, timedelta, timezone
import streamlit as st
from auth import get_supabase

# ============================================================
# Cache 策略：
#   - User settings / plan：60s TTL（變化少）
#   - Usage stats：30s TTL（半實時）
#   - Meetings list / dashboard：30s TTL
#   - 任何 mutation 之後 call invalidate_cache()
# ============================================================
def invalidate_meeting_cache():
    """新增 / 修改 / 刪 meeting 後 call - 只清相關 cache"""
    try:
        list_meetings.clear()
        get_dashboard_stats.clear()
        get_monthly_usage_seconds.clear()
        get_daily_usage_seconds.clear()
        get_summaries_for_wordcloud.clear()
    except Exception:
        pass


def invalidate_user_cache():
    """改 plan / settings 之後 call - 只清 user-level cache"""
    try:
        get_user_plan.clear()
        get_user_settings.clear()
    except Exception:
        pass


# Backward compat
def invalidate_cache():
    invalidate_meeting_cache()

# Free tier 限額
FREE_MONTHLY_SECONDS = 6000        # 100 min/月
FREE_DAILY_SECONDS = 900           # 15 min/日

# Pro tier 限額
PRO_MONTHLY_SECONDS = 12000        # 200 min/月
PRO_DAILY_SECONDS = 1800           # 30 min/日

# Single file 限制
MAX_SINGLE_FILE_SECONDS = 3600     # 單一檔案最多 1 小時


def save_meeting(user_id: str, summary: str, transcript: str = "",
                 client: str = None, project: str = None,
                 duration_seconds: float = 0,
                 audio_filename: str = None) -> dict:
    sb = get_supabase()
    payload = {
        "user_id": user_id,
        "summary": summary,
        "transcript": transcript or "",
        "client": client,
        "project": project,
        "duration_seconds": duration_seconds,
        "audio_filename": audio_filename,
    }
    result = sb.table("meetings").insert(payload).execute()
    invalidate_meeting_cache()  # ⚠️ Clear all cached queries after mutation
    return result.data[0] if result.data else {}


@st.cache_data(ttl=30, show_spinner=False)
def list_meetings(user_id: str, limit: int = 50) -> list[dict]:
    """(cached 30s)

    用 deleted_at IS NULL 過濾 soft-deleted meetings，
    咁用戶 delete 完就見唔到，但 usage 計算 (get_monthly/daily_usage_seconds)
    仍然會將 deleted rows 計入 quota — 防止用戶 delete 後刷返額度。
    """
    sb = get_supabase()
    result = (
        sb.table("meetings")
        .select("id, created_at, client, project, duration_seconds, summary")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def search_meetings(
    user_id: str,
    query: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    搜尋過往會議（自動排除 soft-deleted）：
      - 文字 query → match client / project / summary / transcript
      - date_from / date_to → 日期範圍 (inclusive)
    """
    sb = get_supabase()
    q = (
        sb.table("meetings")
        .select("id, created_at, client, project, duration_seconds, summary")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
    )

    if query and query.strip():
        pattern = f"%{query.strip()}%"
        q = q.or_(
            f"client.ilike.{pattern},"
            f"project.ilike.{pattern},"
            f"summary.ilike.{pattern},"
            f"transcript.ilike.{pattern}"
        )

    if date_from:
        q = q.gte("created_at", datetime.combine(date_from, datetime.min.time()).isoformat())
    if date_to:
        # Include the whole "to" day
        end = datetime.combine(date_to, datetime.min.time()) + timedelta(days=1)
        q = q.lt("created_at", end.isoformat())

    result = q.order("created_at", desc=True).limit(limit).execute()
    return result.data or []


def get_meeting(meeting_id: str, user_id: str) -> dict | None:
    """攞單一 meeting（會 hide soft-deleted — 用戶唔應該再 access 已刪嘅）"""
    sb = get_supabase()
    result = (
        sb.table("meetings")
        .select("*")
        .eq("id", meeting_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    return result.data


def delete_meeting(meeting_id: str, user_id: str):
    """Soft delete: 標記 deleted_at = NOW()，row 仍喺度，咁:
      - 用戶 history / dashboard / search 都見唔到
      - 但 monthly / daily usage 仍然計入呢段 duration（防止刷額度）
    """
    sb = get_supabase()
    sb.table("meetings").update(
        {"deleted_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", meeting_id).eq("user_id", user_id).is_(
        "deleted_at", "null"
    ).execute()
    invalidate_meeting_cache()


def update_meeting_summary(meeting_id: str, user_id: str,
                            new_summary: str,
                            additional_duration: float = 0) -> None:
    """Update meeting 嘅 summary（用於繼續會議合併）。Defensively 唔操作 soft-deleted。"""
    sb = get_supabase()
    # 攞返原本 duration
    existing = (
        sb.table("meetings")
        .select("duration_seconds")
        .eq("id", meeting_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    if not existing.data:
        return
    new_duration = (existing.data[0].get("duration_seconds") or 0) + additional_duration

    sb.table("meetings").update({
        "summary": new_summary,
        "duration_seconds": new_duration,
    }).eq("id", meeting_id).eq("user_id", user_id).is_(
        "deleted_at", "null"
    ).execute()
    invalidate_meeting_cache()


# === Usage / Free tier checking ===

@st.cache_data(ttl=60, show_spinner=False)
def get_user_plan(user_id: str) -> str:
    """Returns 'free' | 'pro' | 'team' (cached 60s)"""
    sb = get_supabase()
    result = (
        sb.table("user_plans")
        .select("plan")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["plan"]
    return "free"


# ============================================================
# User settings (#2 Custom GPT per company)
# ============================================================
INDUSTRIES = {
    "generic": "🏢 一般商務",
    "accounting": "📊 會計 / 審計",
    "legal": "⚖️ 法律",
    "medical": "🏥 醫療",
    "sales": "💼 銷售",
    "education": "🎓 教育",
    "real_estate": "🏘️ 地產",
    "finance": "💰 金融",
    "consulting": "💡 顧問",
    "tech": "💻 科技",
}

SUMMARY_LENGTHS = {
    "short": "短（1 段，~150 字）",
    "medium": "中（標準格式）",
    "full": "長（包埋 quote + 細節）",
}


@st.cache_data(ttl=60, show_spinner=False)
def get_user_settings(user_id: str) -> dict:
    """攞用戶設定（jargon、industry、length、telegram_chat_id 等） (cached 60s)"""
    sb = get_supabase()
    result = (
        sb.table("user_plans")
        .select("company_name, industry, jargon, summary_length, telegram_chat_id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if result.data:
        row = result.data[0]
        return {
            "company_name": row.get("company_name") or "",
            "industry": row.get("industry") or "generic",
            "jargon": row.get("jargon") or "",
            "summary_length": row.get("summary_length") or "medium",
            "telegram_chat_id": row.get("telegram_chat_id") or "",
        }
    return {
        "company_name": "",
        "industry": "generic",
        "jargon": "",
        "summary_length": "medium",
        "telegram_chat_id": "",
    }


# ============================================================
# Invite codes (beta tester gating + auto-upgrade)
# ============================================================
def validate_invite_code(code: str) -> tuple[bool, str]:
    """Check if invite code exists and is unused.
    Returns (is_valid, message_or_target_plan).
    """
    if not code or not code.strip():
        return False, "請填邀請碼"
    sb = get_supabase()
    try:
        result = (
            sb.table("invite_codes")
            .select("code, used_by_user_id, auto_upgrade_to")
            .eq("code", code.strip())
            .limit(1)
            .execute()
        )
        if not result.data:
            return False, "邀請碼唔啱"
        row = result.data[0]
        if row.get("used_by_user_id"):
            return False, "呢個邀請碼已經用咗"
        return True, row.get("auto_upgrade_to") or "pro"
    except Exception as e:
        return False, f"驗證邀請碼失敗：{e}"


def claim_invite_code_and_upgrade(code: str, user_id: str = None, target_plan: str = "pro") -> tuple[bool, str]:
    """Call claim_invite_code RPC (SECURITY DEFINER, atomic, race-safe).

    RPC uses auth.uid() internally + code.auto_upgrade_to for plan.
    user_id / target_plan args 保留只為 backwards compat (ignored).
    Returns (success, plan_or_error_msg).
    """
    if not code or not code.strip():
        return False, "邀請碼為空"
    sb = get_supabase()
    try:
        result = sb.rpc("claim_invite_code", {"p_code": code.strip()}).execute()
        data = result.data
        # supabase-py 對於 jsonb-returning function 通常 return dict 直接
        # (有啲版本會 wrap 喺 list 度，安全 unwrap)
        if isinstance(data, list) and data:
            payload = data[0]
        elif isinstance(data, dict):
            payload = data
        else:
            return False, f"RPC 返回未預期格式：{data!r}"

        if payload.get("ok"):
            invalidate_user_cache()
            return True, payload.get("plan", "pro")
        return False, payload.get("error") or "邀請碼啟用失敗（未知原因）"
    except Exception as e:
        return False, f"系統錯誤：{e}"


def create_telegram_link_code(user_id: str, ttl_minutes: int = 10) -> str:
    """生成一條一次性 Telegram 連接碼，10 分鐘有效。

    User 撳「連接 Telegram」嘅 button → 我哋 generate 個 6 位 code → 插落
    telegram_link_codes table → 用戶 click https://t.me/Bot?start=<code>
    → bot webhook (Edge Function) 用個 code 揾返 user_id → 設 chat_id 落
    user_plans。
    """
    import secrets as _secrets
    import string as _string
    code = "".join(
        _secrets.choice(_string.ascii_uppercase + _string.digits)
        for _ in range(6)
    )
    expires = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    sb = get_supabase()
    sb.table("telegram_link_codes").insert({
        "code": code,
        "user_id": user_id,
        "expires_at": expires.isoformat(),
    }).execute()
    return code


def update_user_settings(user_id: str, **kwargs) -> None:
    """Update user 設定。允許 fields: company_name, industry, jargon, summary_length, telegram_chat_id"""
    allowed = {"company_name", "industry", "jargon", "summary_length", "telegram_chat_id"}
    update_data = {k: v for k, v in kwargs.items() if k in allowed}
    if not update_data:
        return
    sb = get_supabase()
    sb.table("user_plans").update(update_data).eq("user_id", user_id).execute()
    invalidate_user_cache()


# ============================================================
# Dashboard analytics (#6)
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_dashboard_stats(user_id: str) -> dict:
    """攞 dashboard 統計（**唔 fetch summary text**，加快 10x）

    TTL 5 分鐘 — 任何 meeting mutation 都會 invalidate_meeting_cache(),
    所以唔需要短 TTL 保鮮，dashboard 開頁可以行 cache hit 唔再 query DB.

    Soft-deleted 唔計入 dashboard（用戶 delete 完就唔想再見到統計入面），
    但 monthly/daily usage 函數會計入 — 兩者分開。
    """
    sb = get_supabase()
    # 只 select metadata fields - 唔好 fetch summary（大）
    result = (
        sb.table("meetings")
        .select("id, created_at, client, project, duration_seconds")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=False)
        .execute()
    )
    meetings = result.data or []

    total_count = len(meetings)
    total_seconds = sum(m.get("duration_seconds", 0) or 0 for m in meetings)

    from collections import Counter
    client_counter = Counter(m.get("client") for m in meetings if m.get("client"))
    project_counter = Counter(m.get("project") for m in meetings if m.get("project"))

    monthly = Counter()
    for m in meetings:
        try:
            month = m["created_at"][:7]
            monthly[month] += 1
        except Exception:
            pass

    return {
        "total_count": total_count,
        "total_minutes": total_seconds / 60,
        "total_hours": total_seconds / 3600,
        "top_clients": client_counter.most_common(10),
        "top_projects": project_counter.most_common(10),
        "monthly_counts": dict(sorted(monthly.items())),
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_summaries_for_wordcloud(user_id: str) -> str:
    """獨立 query 攞 summary text - 只喺用戶撳「生成詞雲」時先 call。
    Soft-deleted 唔計（用戶唔想睇）。
    """
    sb = get_supabase()
    result = (
        sb.table("meetings")
        .select("summary")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return "\n\n".join(m.get("summary", "") for m in (result.data or []))


@st.cache_data(ttl=5, show_spinner=False)
def get_monthly_usage_seconds(user_id: str) -> float:
    """Returns total seconds processed this calendar month (cached 5s).

    短 TTL = web app 用戶可以快啲 see Telegram bot 嘅 changes (因為 Edge
    Function 唔可以直接 invalidate Python in-memory cache, 只有 TTL 過期
    先見到變化). 5s 對 DB load 影響微 (每用戶 ~12 queries / min).

    ⚠️ **故意唔 filter deleted_at**：呢個係 quota 計算，soft-deleted
    嘅 meeting 一樣要計入用戶今個月用咗幾多 (防止刷額度 -- delete 完
    可以再 transcribe)。Dashboard / list 啲 query 先會 filter
    deleted_at。
    """
    sb = get_supabase()
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = (
        sb.table("meetings")
        .select("duration_seconds")
        .eq("user_id", user_id)
        .gte("created_at", month_start.isoformat())
        .execute()
    )
    return sum(m.get("duration_seconds", 0) or 0 for m in (result.data or []))


@st.cache_data(ttl=5, show_spinner=False)
def get_daily_usage_seconds(user_id: str) -> float:
    """Returns total seconds processed today (cached 5s).

    同 get_monthly_usage_seconds：故意計埋 soft-deleted (見上面註解);
    TTL 短啲 (5s) 為咗 Telegram bot save meeting 之後 web app 能夠
    快啲 see 到 counter 更新.
    """
    sb = get_supabase()
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    result = (
        sb.table("meetings")
        .select("duration_seconds")
        .eq("user_id", user_id)
        .gte("created_at", day_start.isoformat())
        .execute()
    )
    return sum(m.get("duration_seconds", 0) or 0 for m in (result.data or []))


def can_process(user_id: str, audio_duration_seconds: float) -> tuple[bool, str]:
    """Check if user can process this audio under their plan (monthly + daily + single file)"""
    # === 1. Single file size check (abuse prevention) ===
    if audio_duration_seconds > MAX_SINGLE_FILE_SECONDS:
        max_hr = MAX_SINGLE_FILE_SECONDS / 3600
        file_hr = audio_duration_seconds / 3600
        return False, (
            f"⚠️ 單一檔案最多 {max_hr:.0f} 小時，"
            f"你呢個檔案 {file_hr:.1f} 小時，太長。\n"
            f"請將錄音 split 做幾段。"
        )

    plan = get_user_plan(user_id)

    # === 2. Daily limit (per plan) ===
    daily_limit = PRO_DAILY_SECONDS if plan in ("pro", "team") else FREE_DAILY_SECONDS
    daily_used = get_daily_usage_seconds(user_id)
    daily_remaining = daily_limit - daily_used

    if audio_duration_seconds > daily_remaining:
        used_min = daily_used / 60
        rem_min = max(daily_remaining, 0) / 60
        return False, (
            f"⚠️ {plan.upper()} 版每日上限 {daily_limit/60:.0f} 分鐘。\n"
            f"你今日已用 {used_min:.1f} 分鐘，剩 {rem_min:.1f} 分鐘。\n"
            f"明日 0:00 UTC（香港 8am）重置。\n"
            + ("👉 升級 Pro 解鎖更高上限。" if plan == "free" else "")
        )

    # === 3. Monthly limit (free only) ===
    if plan in ("pro", "team"):
        return True, ""

    monthly_used = get_monthly_usage_seconds(user_id)
    monthly_remaining = FREE_MONTHLY_SECONDS - monthly_used

    if audio_duration_seconds > monthly_remaining:
        used_min = monthly_used / 60
        rem_min = max(monthly_remaining, 0) / 60
        return False, (
            f"⚠️ 免費版每月 {FREE_MONTHLY_SECONDS/60:.0f} 分鐘已用完。\n"
            f"你已用 {used_min:.1f} 分鐘，剩 {rem_min:.1f} 分鐘。\n\n"
            f"👉 升級 Pro 即解鎖無限用量。"
        )

    return True, ""
