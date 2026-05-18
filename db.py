"""Supabase DB queries for meetings + usage tracking"""
from datetime import date, datetime, timedelta, timezone
import streamlit as st
from auth import get_supabase

# Free tier 限額
FREE_MONTHLY_SECONDS = 1800        # 30 min/月
FREE_DAILY_SECONDS = 600           # 10 min/日（防一次過用晒）

# Pro tier 限額（防 abuse / cost burning）
PRO_MONTHLY_SECONDS = float("inf")
PRO_DAILY_SECONDS = 14400          # 4 小時/日 上限（防盜用）

# Single file 限制
MAX_SINGLE_FILE_SECONDS = 7200     # 單一檔案最多 2 小時


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
    return result.data[0] if result.data else {}


def list_meetings(user_id: str, limit: int = 50) -> list[dict]:
    sb = get_supabase()
    result = (
        sb.table("meetings")
        .select("id, created_at, client, project, duration_seconds, summary")
        .eq("user_id", user_id)
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
    搜尋過往會議：
      - 文字 query → match client / project / summary / transcript
      - date_from / date_to → 日期範圍 (inclusive)
    """
    sb = get_supabase()
    q = (
        sb.table("meetings")
        .select("id, created_at, client, project, duration_seconds, summary")
        .eq("user_id", user_id)
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
    sb = get_supabase()
    result = (
        sb.table("meetings")
        .select("*")
        .eq("id", meeting_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return result.data


def delete_meeting(meeting_id: str, user_id: str):
    sb = get_supabase()
    sb.table("meetings").delete().eq("id", meeting_id).eq("user_id", user_id).execute()


# === Usage / Free tier checking ===

def get_user_plan(user_id: str) -> str:
    """Returns 'free' | 'pro' | 'team'"""
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


def get_user_settings(user_id: str) -> dict:
    """攞用戶設定（jargon、industry、length 等）"""
    sb = get_supabase()
    result = (
        sb.table("user_plans")
        .select("company_name, industry, jargon, summary_length")
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
        }
    return {
        "company_name": "",
        "industry": "generic",
        "jargon": "",
        "summary_length": "medium",
    }


def update_user_settings(user_id: str, **kwargs) -> None:
    """Update user 設定。允許 fields: company_name, industry, jargon, summary_length"""
    allowed = {"company_name", "industry", "jargon", "summary_length"}
    update_data = {k: v for k, v in kwargs.items() if k in allowed}
    if not update_data:
        return
    sb = get_supabase()
    sb.table("user_plans").update(update_data).eq("user_id", user_id).execute()


# ============================================================
# Dashboard analytics (#6)
# ============================================================
def get_dashboard_stats(user_id: str) -> dict:
    """攞 dashboard 統計：總會議數、總分鐘、top clients/projects"""
    sb = get_supabase()
    result = (
        sb.table("meetings")
        .select("id, created_at, client, project, duration_seconds, summary")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .execute()
    )
    meetings = result.data or []

    total_count = len(meetings)
    total_seconds = sum(m.get("duration_seconds", 0) or 0 for m in meetings)

    # Client / project 統計
    from collections import Counter
    client_counter = Counter(m.get("client") for m in meetings if m.get("client"))
    project_counter = Counter(m.get("project") for m in meetings if m.get("project"))

    # 月份 trend
    monthly = Counter()
    for m in meetings:
        try:
            month = m["created_at"][:7]  # YYYY-MM
            monthly[month] += 1
        except Exception:
            pass

    # All summary text（俾 word cloud）
    all_summaries = "\n\n".join(m.get("summary", "") for m in meetings)

    return {
        "total_count": total_count,
        "total_minutes": total_seconds / 60,
        "total_hours": total_seconds / 3600,
        "top_clients": client_counter.most_common(10),
        "top_projects": project_counter.most_common(10),
        "monthly_counts": dict(sorted(monthly.items())),
        "all_summaries_text": all_summaries,
        "meetings": meetings,
    }


def get_monthly_usage_seconds(user_id: str) -> float:
    """Returns total seconds processed this calendar month"""
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


def get_daily_usage_seconds(user_id: str) -> float:
    """Returns total seconds processed today (UTC midnight)"""
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
