"""Generate .ics calendar file from action items
任何 calendar app（Google / Outlook / Apple）都 import 得"""
from datetime import date, datetime, timedelta


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
