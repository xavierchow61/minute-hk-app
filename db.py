"""Supabase DB queries for meetings + usage tracking"""
from datetime import datetime, timezone
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
