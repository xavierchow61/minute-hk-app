"""Generate .ics calendar file + Google/Outlook deep link URLs
- ICS：universal download
- Google Calendar link：一鍵 add 到用戶 Google Calendar
- Outlook link：一鍵 add 到 outlook.live.com / Microsoft 365
"""
from datetime import date, datetime, timedelta
from urllib.parse import quote


def _escape(text: str) -> str:
    """Escape special chars for ICS format"""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def _parse_deadline(deadline: str | None) -> date:
    """Parse deadline string, fallback to today+7d"""
    if deadline:
        try:
            return date.fromisoformat(deadline)
        except (ValueError, TypeError):
            pass
    return date.today() + timedelta(days=7)


def _build_description(item: dict, client: str = "", meeting_title: str = "") -> str:
    """Build event description for an action item"""
    parts = []
    if client:
        parts.append(f"客戶: {client}")
    parts.append(f"負責人: {item.get('assignee') or '—'}")
    parts.append(f"優先級: {item.get('priority') or 'medium'}")
    if meeting_title:
        parts.append(f"來自會議: {meeting_title}")
    parts.append("")
    parts.append("由 Minute.hk 自動生成")
    return "\n".join(parts)


# ============================================================
# 🟦 Google Calendar deep link (一鍵 add，唔需要 OAuth)
# ============================================================
def google_calendar_url(item: dict, client: str = "", meeting_title: str = "") -> str:
    """生成 Google Calendar event URL（用戶 click 即可 add）"""
    due = _parse_deadline(item.get("deadline"))
    next_day = due + timedelta(days=1)
    # All-day event format: YYYYMMDD/YYYYMMDD
    dates = f"{due.strftime('%Y%m%d')}/{next_day.strftime('%Y%m%d')}"

    priority_emoji = {
        "high": "🔴", "medium": "🟡", "low": "🟢"
    }.get((item.get("priority") or "").lower(), "")
    title = f"{priority_emoji} {item.get('task') or '會議跟進'}".strip()
    desc = _build_description(item, client, meeting_title)

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates,
        "details": desc,
    }
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"https://calendar.google.com/calendar/render?{qs}"


# ============================================================
# 🟪 Outlook deep link (Outlook.com / Microsoft 365)
# ============================================================
def outlook_calendar_url(item: dict, client: str = "", meeting_title: str = "") -> str:
    """生成 Outlook event URL"""
    due = _parse_deadline(item.get("deadline"))
    # Use 9am-10am for default times
    startdt = due.strftime("%Y-%m-%dT09:00:00")
    enddt = due.strftime("%Y-%m-%dT10:00:00")

    priority_emoji = {
        "high": "🔴", "medium": "🟡", "low": "🟢"
    }.get((item.get("priority") or "").lower(), "")
    title = f"{priority_emoji} {item.get('task') or '會議跟進'}".strip()
    desc = _build_description(item, client, meeting_title)

    params = {
        "path": "/calendar/action/compose",
        "rru": "addevent",
        "subject": title,
        "body": desc,
        "startdt": startdt,
        "enddt": enddt,
    }
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"https://outlook.live.com/calendar/0/deeplink/compose?{qs}"


def action_items_to_ics(
    action_items: list[dict],
    meeting_title: str = "會議",
    client: str = "",
) -> bytes:
    """
    轉換 action items list 做 .ics 檔案 bytes

    Args:
        action_items: List of {task, assignee, deadline, priority}
        meeting_title: 會議名稱
        client: 客戶名（會放入 description）
    """
    now = datetime.utcnow()
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Minute.hk//Cantonese Meeting AI//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Minute.hk - {meeting_title}",
    ]

    for i, item in enumerate(action_items):
        task = item.get("task") or "（無描述）"
        assignee = item.get("assignee") or "—"
        priority = item.get("priority") or "medium"
        deadline = item.get("deadline")

        # 解析 deadline；如果冇 → 用 7 日後做 default
        if deadline:
            try:
                due_date = date.fromisoformat(deadline)
            except (ValueError, TypeError):
                due_date = date.today() + timedelta(days=7)
        else:
            due_date = date.today() + timedelta(days=7)

        # 用 all-day event 格式
        date_str = due_date.strftime("%Y%m%d")
        end_date_str = (due_date + timedelta(days=1)).strftime("%Y%m%d")

        uid = f"{now.timestamp()}-{i}-minutehk@minute.hk"
        priority_map = {"high": "1", "medium": "5", "low": "9"}
        ics_priority = priority_map.get(priority.lower(), "5")
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority.lower(), "")

        # Build description
        desc_parts = []
        if client:
            desc_parts.append(f"客戶: {client}")
        desc_parts.append(f"負責人: {assignee}")
        desc_parts.append(f"優先級: {priority}")
        desc_parts.append(f"來自會議: {meeting_title}")
        desc_parts.append("")
        desc_parts.append("由 Minute.hk 自動生成")
        description = _escape("\n".join(desc_parts))

        summary = _escape(f"{priority_emoji} {task}".strip())

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{timestamp}",
            f"DTSTART;VALUE=DATE:{date_str}",
            f"DTEND;VALUE=DATE:{end_date_str}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            f"PRIORITY:{ics_priority}",
            "TRANSP:TRANSPARENT",  # 唔阻 busy time
            # Reminder 1 日前
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "DESCRIPTION:Reminder",
            "TRIGGER:-PT24H",
            "END:VALARM",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")

    # ICS 標準要求 CRLF line endings
    return "\r\n".join(lines).encode("utf-8")
