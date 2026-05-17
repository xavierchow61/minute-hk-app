"""Supabase DB queries for meetings + usage tracking"""
from datetime import datetime, timezone
import streamlit as st
from auth import get_supabase

# Free tier limit: 30 分鐘 = 1800 秒/月
FREE_MONTHLY_SECONDS = 1800
PRO_MONTHLY_SECONDS = float("inf")


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


def can_process(user_id: str, audio_duration_seconds: float) -> tuple[bool, str]:
    """Check if user can process this audio under their plan"""
    plan = get_user_plan(user_id)
    if plan == "pro" or plan == "team":
        return True, ""

    used = get_monthly_usage_seconds(user_id)
    limit = FREE_MONTHLY_SECONDS
    remaining = limit - used

    if audio_duration_seconds > remaining:
        used_min = used / 60
        rem_min = max(remaining, 0) / 60
        audio_min = audio_duration_seconds / 60
        return False, (
            f"⚠️ 免費版每月 {limit/60:.0f} 分鐘，"
            f"你已用 {used_min:.1f} 分鐘，剩 {rem_min:.1f} 分鐘。\n"
            f"今次嗰個檔案 {audio_min:.1f} 分鐘，超出限額。\n\n"
            f"👉 升級 Pro 解鎖無限用量。"
        )
    return True, ""
