"""Gemini transcribe + summarize + translate + sentiment for cloud"""
import io
import tempfile
import time
from pathlib import Path

import streamlit as st
from google import genai
from google.genai import types

GEMINI_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ["gemini-2.0-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
INLINE_MAX_BYTES = 18 * 1024 * 1024   # < 20MB Gemini inline limit, leave headroom


# ============================================================
# 🔁 Retry helper for transient 503 / overload errors
# ============================================================
def _is_retryable(e: Exception) -> bool:
    """Check if exception is transient (503 / overload / rate limit)"""
    msg = str(e).lower()
    return any(s in msg for s in [
        "503", "unavailable", "overload", "high demand",
        "deadline exceeded", "504", "internal error", "500",
    ])


def call_with_retry(fn, *args, max_attempts: int = 3,
                    base_delay: float = 2.0, fallback_models: list = None,
                    **kwargs):
    """
    Call Gemini API with retry on transient errors + fallback to alt models.

    Args:
        fn: function to call (takes 'model' kwarg)
        max_attempts: total tries with primary model
        base_delay: starting delay seconds (doubles each retry)
        fallback_models: list of models to try after primary fails
    """
    fallback_models = fallback_models or FALLBACK_MODELS
    primary = kwargs.get("model", GEMINI_MODEL)

    last_error = None

    # Try primary model with retries
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            if not _is_retryable(e):
                raise
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)

    # Try fallback models (1 try each)
    for fb_model in fallback_models:
        if fb_model == primary:
            continue
        try:
            kwargs["model"] = fb_model
            return fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            if not _is_retryable(e):
                raise

    # All exhausted
    raise last_error

# 翻譯支援嘅語言
TRANSLATE_TARGETS = {
    "en": "English",
    "zh-Hans": "简体中文",
    "ja": "日本語",
    "ko": "한국어",
    "th": "ภาษาไทย",
    "ms": "Bahasa Melayu",
}


def _client():
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


INDUSTRY_PROMPTS = {
    "generic": "你係資深嘅商務會議秘書。",
    "accounting": (
        "你係香港資深會計師樓嘅高級秘書，熟悉會計、審計、稅務、財務報表術語。"
        "識別會議中嘅會計議題（IFRS、HKFRS、profit tax、audit、disclosure 等）。"
    ),
    "legal": "你係香港律師樓嘅 paralegal，熟悉合約、訴訟、合規術語。",
    "medical": "你係醫療專業秘書，熟悉診斷、處方、病歷術語。",
    "sales": "你係銷售團隊嘅 admin，熟悉 pipeline、deal、quota、commission 術語。",
    "education": "你係教育機構嘅 admin，熟悉課程、學生表現、家校溝通術語。",
    "real_estate": "你係地產業 admin，熟悉樓盤、租務、按揭、估價術語。",
    "finance": "你係金融機構秘書，熟悉投資、風險、合規、產品術語。",
    "consulting": "你係顧問公司 PA，熟悉 strategy、deliverable、stakeholder 術語。",
    "tech": "你係科技公司 PM 助手，熟悉 product、sprint、roadmap、metrics 術語。",
}

LENGTH_INSTRUCTIONS = {
    "short": "用最簡短嘅 1-2 段文字總結（~150 字），重點 + action items，唔需要分 sections。",
    "medium": "用標準格式：會議重點 + 主要議題 + 決議 + Action Items + 風險。",
    "full": "用詳細格式：包含晒所有 sections、保留 client 講過嘅重要原話（quotes）、識別暗示嘅 concerns。",
}


def build_summary_prompt(duration: str, client_info: str,
                         industry: str = "generic",
                         length: str = "medium",
                         custom_jargon: str = "",
                         company_name: str = "") -> str:
    """建立可定制嘅 summary prompt"""
    system = INDUSTRY_PROMPTS.get(industry, INDUSTRY_PROMPTS["generic"])
    length_instr = LENGTH_INSTRUCTIONS.get(length, LENGTH_INSTRUCTIONS["medium"])

    custom_context = ""
    if company_name:
        custom_context += f"\n你嘅僱主公司：{company_name}。"
    if custom_jargon:
        custom_context += f"\n你公司常用嘅特殊術語/人名：{custom_jargon}（識別錄音時請特別留意呢啲詞）。"

    if length == "short":
        format_block = """
請用以下 Markdown 格式輸出（簡短版）：

# 📝 會議紀要

**會議時長**：{duration}  **客戶/項目**：{client_info}

## 🎯 重點摘要
（1-2 段，~150 字）

## ✅ Action Items
- ...

---
*由 AI 自動生成*"""

    elif length == "full":
        format_block = """
請用以下 Markdown 格式輸出（詳細版）：

# 📝 會議紀要

## 📅 基本資訊
- **錄音時長**：{duration}
- **客戶/項目**：{client_info}

## 🎯 會議重點（Executive Summary）
（3-5 句總結俾趕時間嘅人睇）

## 💡 主要討論議題
1. **[議題]**
   - 背景
   - 關鍵討論
   - 結論

## 📜 重要原話 (Quotes)
> 「...」— 講者
> 「...」— 講者

## ✅ 決議事項
- ...

## 📋 Action Items
| # | 待辦事項 | 負責人 | Deadline | 優先級 |
|---|---------|--------|----------|--------|
| 1 | ... | ... | ... | 🔴高/🟡中/🟢低 |

## ⚠️ 風險與跟進
- [明確風險]
- [隱性 concerns（client 冇明講但暗示嘅嘢）]

## 💡 觀察 / 建議
- [我建議跟進嘅事項]

---
*由 AI 自動生成*"""
    else:  # medium
        format_block = """
請用以下 Markdown 格式輸出：

# 📝 會議紀要

## 📅 基本資訊
- **錄音時長**：{duration}
- **客戶/項目**：{client_info}

## 🎯 會議重點
（3-5 句 executive summary）

## 💡 主要討論議題
1. **[議題]**
   - [關鍵討論]

## ✅ 決議事項
- [決議]

## 📋 Action Items
| # | 待辦事項 | 負責人 | Deadline | 優先級 |
|---|---------|--------|----------|--------|
| 1 | ... | ... | ... | 🔴高/🟡中/🟢低 |

## ⚠️ 風險與跟進
- [風險]

---
*由 AI 自動生成*"""

    return f"""{system}{custom_context}

呢段係一段會議錄音，可能係廣東話、普通話或英文（或夾雜）。

任務：
1. 聽錄音內容，理解口語講嘅嘢
2. 用**書面繁體中文**整理（保留英文專業術語）
3. {length_instr}

{format_block.format(duration=duration, client_info=client_info)}"""


def _ext_from_mime(mime_type: str) -> str:
    return {
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/ogg": ".ogg",
        "audio/flac": ".flac",
        "audio/webm": ".webm",
        "video/mp4": ".mp4",
    }.get(mime_type, ".bin")


def process_audio(audio_bytes: bytes, mime_type: str,
                  client_name: str = "", project_name: str = "",
                  industry: str = "generic", length: str = "medium",
                  custom_jargon: str = "", company_name: str = "") -> dict:
    """
    一個 Gemini call 完成：transcribe + summarize
    支援 industry-specific prompt + 多長度 + custom jargon
    """
    client = _client()
    size_mb = len(audio_bytes) / (1024 * 1024)

    # Build client info
    client_info = ""
    if client_name:
        client_info += f"客戶 {client_name}"
    if project_name:
        client_info += f" / 項目 {project_name}" if client_info else f"項目 {project_name}"
    if not client_info:
        client_info = "—"

    prompt = build_summary_prompt(
        duration="（請根據錄音實際長度填寫）",
        client_info=client_info,
        industry=industry,
        length=length,
        custom_jargon=custom_jargon,
        company_name=company_name,
    )

    # === 小檔案：inline data（最快） ===
    if len(audio_bytes) <= INLINE_MAX_BYTES:
        def _gen_inline(model=GEMINI_MODEL):
            return client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                ],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                ),
            )
        response = call_with_retry(_gen_inline, model=GEMINI_MODEL)
        return {"summary": response.text, "model": GEMINI_MODEL, "method": "inline"}

    # === 大檔案：Files API upload ===
    ext = _ext_from_mime(mime_type)
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        audio_file = client.files.upload(file=str(tmp_path))

        # 等檔案 state 變 ACTIVE（Gemini 有時要 process 幾秒）
        for _ in range(60):
            if hasattr(audio_file, "state") and getattr(audio_file.state, "name", "") == "ACTIVE":
                break
            time.sleep(1)
            audio_file = client.files.get(name=audio_file.name)

        def _gen_files(model=GEMINI_MODEL):
            return client.models.generate_content(
                model=model,
                contents=[prompt, audio_file],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                ),
            )
        response = call_with_retry(_gen_files, model=GEMINI_MODEL)

        # 清理 cloud file
        try:
            client.files.delete(name=audio_file.name)
        except Exception:
            pass

        return {"summary": response.text, "model": GEMINI_MODEL, "method": "files_api"}

    finally:
        tmp_path.unlink(missing_ok=True)


# ============================================================
# 🌐 翻譯 (Translation)
# ============================================================
TRANSLATE_PROMPT = """請將以下會議紀要翻譯成 {target_name}。

要求：
1. 保留原本嘅 Markdown 格式（headings、tables、bullet points）
2. 商務 / 專業用語翻譯要準確
3. 人名、公司名、項目代號保持原文（唔好譯）
4. 日期、數字、貨幣保留原樣
5. 自然流暢，唔好直譯

原文 (廣東話 / 中英夾雜):
{summary}

只輸出翻譯結果，唔需要其他說明。"""


def translate(summary_md: str, target_code: str) -> str:
    """翻譯會議紀要"""
    target_name = TRANSLATE_TARGETS.get(target_code, target_code)
    client = _client()

    def _gen(model=GEMINI_MODEL):
        return client.models.generate_content(
            model=model,
            contents=TRANSLATE_PROMPT.format(
                target_name=target_name,
                summary=summary_md,
            ),
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
            ),
        )
    response = call_with_retry(_gen, model=GEMINI_MODEL)
    return response.text


# ============================================================
# 🎭 語氣分析 (Sentiment / Tone Analysis)
# ============================================================
SENTIMENT_PROMPT = """你係資深商業心理顧問。請根據以下會議紀要，分析會議嘅語氣同氣氛。

用書面繁體中文回答，格式如下：

## 🎭 語氣分析報告

### 📊 整體氣氛
- **氛圍**: （友好 / 中性 / 緊張 / 衝突 / 焦慮）
- **能量**: （高 / 中 / 低）
- **建設性**: （正面 / 中性 / 負面）

### 👤 對方語氣
- 客戶 / 與會者對你嘅態度
- 有冇明顯嘅 frustration / 抱怨
- 有冇暗示嘅紅旗 (hidden complaints)
- 對方最在意嘅事項

### 📈 機會 vs 風險
- ✅ 正面信號（potential upsell, satisfaction, trust）
- ⚠️ 風險信號（churn risk, dissatisfaction, scope creep）

### 🎯 跟進建議
- 即時 follow-up 嘅 action items
- 需要特別小心嘅地方
- 建議下次溝通嘅 tone

---

會議紀要:
{summary}"""


def analyze_sentiment(summary_md: str) -> str:
    """分析會議語氣 / 氣氛"""
    client = _client()

    def _gen(model=GEMINI_MODEL):
        return client.models.generate_content(
            model=model,
            contents=SENTIMENT_PROMPT.format(summary=summary_md),
            config=types.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=4096,
            ),
        )
    response = call_with_retry(_gen, model=GEMINI_MODEL)
    return response.text


# ============================================================
# 🔗 兩會議綜合 / 繼續補充 (#1)
# ============================================================
MERGE_PROMPT = """你係資深商務秘書。以下係同一個 client / project 嘅兩段會議紀要。
請將兩段合併成一份**綜合紀要**，整理時序。

【會議 1（較早）】
{old_summary}

---

【會議 2（最新）】
{new_summary}

要求：
1. 用**書面繁體中文**，保留 Markdown 格式
2. **保留兩次嘅所有 action items**：
   - 重複嘅 → 合併 + 標「已重申」
   - 完成嘅 → 標「✓ 已完成」
   - 更新嘅 → 標「（之前 X，現改為 Y）」
3. 如果決議有變 → 最新嗰份優先 + 標明變動
4. 加一個 **「📅 會議時序」** section 列出兩次會議嘅 chronological
5. 用之前 same 嘅 Markdown 格式輸出（會議重點、議題、決議、Action Items、風險）

只輸出合併紀要，唔需要其他說明。"""


def merge_summaries(old_summary: str, new_summary: str) -> str:
    """合併兩段會議紀要做綜合版"""
    client = _client()

    def _gen(model=GEMINI_MODEL):
        return client.models.generate_content(
            model=model,
            contents=MERGE_PROMPT.format(
                old_summary=old_summary,
                new_summary=new_summary,
            ),
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
            ),
        )
    response = call_with_retry(_gen, model=GEMINI_MODEL)
    return response.text


# ============================================================
# 📅 Structured Action Items (for Calendar export)
# ============================================================
import json
from datetime import date as _date

ACTION_ITEMS_PROMPT = """從以下會議紀要 extract 所有 action items（待辦事項），轉成 JSON array。

返回格式（嚴格）：
[
  {{
    "task": "具體要做嘅事（簡短）",
    "assignee": "負責人名（如冇就 '—'）",
    "deadline": "YYYY-MM-DD（如冇明確日期，用 null）",
    "priority": "high / medium / low"
  }}
]

注意：
- 今日日期：{today}
- 如果 deadline 係相對日期（「下星期五」「兩星期內」），請推算成具體日期
- 如果完全冇 deadline 或者唔肯定，set null
- 只要 action items（要做嘅事），唔好包括決議事項或風險

紀要：
{summary}

只輸出 valid JSON array，**唔可以有任何其他文字**（包括 markdown code fence）。"""


def extract_action_items(summary_md: str) -> list[dict]:
    """從 summary 抽出結構化 action items + 日期"""
    client = _client()

    def _gen(model=GEMINI_MODEL):
        return client.models.generate_content(
            model=model,
            contents=ACTION_ITEMS_PROMPT.format(
                summary=summary_md,
                today=_date.today().isoformat(),
            ),
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )
    response = call_with_retry(_gen, model=GEMINI_MODEL)
    raw = response.text.strip()
    # 清走可能嘅 markdown code fence
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        items = json.loads(raw)
        return items if isinstance(items, list) else []
    except json.JSONDecodeError:
        return []
