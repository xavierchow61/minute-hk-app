"""Telegram Bot API — outgoing-only message sender.

無 webhook / polling — 純粹用 Bot API 嘅 sendMessage endpoint 推 meeting summary
俾用戶嘅 Telegram chat。用戶要做嘅 setup (一次過)：
  1. Open @BotFather → /newbot → 攞 bot token → 加落 Streamlit secrets
  2. (用戶) 開 @userinfobot 攞自己嘅 numeric chat_id → 入 Settings paste 落
"""
import re
import urllib.parse
import urllib.request
import json
import streamlit as st


TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4000  # Telegram 限 4096，留少少 buffer


def get_bot_token() -> str | None:
    """攞 bot token from Streamlit secrets。Return None 如果未設 / 冇 secrets file。"""
    try:
        return st.secrets.get("TELEGRAM_BOT_TOKEN") or None
    except Exception:
        return None


def is_configured() -> bool:
    """Admin 設咗 bot token 未"""
    return bool(get_bot_token())


def strip_markdown_to_text(md: str) -> str:
    """將 markdown summary 轉做 Telegram-friendly plain text。

    Telegram 嘅 MarkdownV2 escape rules 好嚴格，HTML mode 又限 tags。
    最穩陣係 plain text + emoji preserved + 用 dash 取代 markdown 標記。
    """
    text = md or ""
    # Headers: ## Foo → 【Foo】
    text = re.sub(r"^#{1,6}\s*(.+?)\s*$", r"━━ \1 ━━", text, flags=re.M)
    # Bold **x** → x
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    # Italic *x* or _x_ → x (avoid touching **/__)
    text = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_(?!_)([^_\n]+?)_(?!_)", r"\1", text)
    # Inline code `x` → 「x」
    text = re.sub(r"`([^`\n]+)`", r"「\1」", text)
    # Tables — keep raw markdown; Telegram users will see pipes
    # Bullet markers - / * → •
    text = re.sub(r"^[\-\*]\s+", "• ", text, flags=re.M)
    # Numbered list 1. → keep as-is
    # Horizontal rules ---/=== → blank line
    text = re.sub(r"^[\-=]{3,}$", "", text, flags=re.M)
    # 多個空行壓縮做 2 個
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def send_message(chat_id: str, text: str) -> tuple[bool, str]:
    """經 Telegram Bot API 推一條 message 俾指定 chat_id.

    超過 4000 char 自動分多條 send (Telegram 4096 limit)。
    Return (ok, info_or_error_msg).
    """
    token = get_bot_token()
    if not token:
        return False, "Bot token 未 setup（admin 要喺 Streamlit secrets 加 TELEGRAM_BOT_TOKEN）"
    if not chat_id:
        return False, "未連接 Telegram，請喺設定加 chat ID"

    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    # 分段
    chunks: list[str] = []
    remaining = text
    while len(remaining) > MAX_MESSAGE_LENGTH:
        # 喺最近嘅換行位 split (避免切斷一句中間)
        split_at = remaining.rfind("\n", 0, MAX_MESSAGE_LENGTH)
        if split_at < MAX_MESSAGE_LENGTH // 2:
            split_at = MAX_MESSAGE_LENGTH  # 真係搵唔到換行就硬切
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)

    for i, chunk in enumerate(chunks):
        prefix = f"📄 ({i+1}/{len(chunks)}) " if len(chunks) > 1 else ""
        payload = json.dumps(
            {"chat_id": chat_id, "text": prefix + chunk, "disable_web_page_preview": True}
        ).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            body = json.loads(resp.read().decode("utf-8"))
            if not body.get("ok"):
                return False, f"Telegram API error: {body.get('description', 'unknown')}"
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8"))
                desc = err_body.get("description", str(e))
            except Exception:
                desc = str(e)
            if "chat not found" in desc.lower():
                return False, (
                    "❌ Chat ID 唔啱 — 用戶未開過個 bot。"
                    "請先去 t.me/your_bot_username 撳 START。"
                )
            if "blocked" in desc.lower():
                return False, "❌ 用戶 block 咗個 bot — 解 block 先"
            return False, f"Telegram HTTP error: {desc}"
        except Exception as e:
            return False, f"Send 失敗: {e}"

    return True, f"已 send {len(chunks)} 條 message 落 Telegram"


def send_summary(chat_id: str, summary_md: str, header: str = "") -> tuple[bool, str]:
    """高階 helper：將 markdown summary 轉換 + send"""
    text = strip_markdown_to_text(summary_md)
    if header:
        text = f"{header}\n\n{text}"
    return send_message(chat_id, text)
