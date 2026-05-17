"""Gemini transcribe + summarize + translate + sentiment for cloud"""
import io
import tempfile
import time
from pathlib import Path

import streamlit as st
from google import genai
from google.genai import types

GEMINI_MODEL = "gemini-2.5-flash"
INLINE_MAX_BYTES = 18 * 1024 * 1024   # < 20MB Gemini inline limit, leave headroom

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


SUMMARY_PROMPT = """你係資深嘅商務會議秘書。

呢段係一段會議錄音，可能係廣東話、普通話或英文（或夾雜）。

任務：
1. 聽錄音內容，理解口語講嘅嘢
2. 用**書面繁體中文**整理成專業會議紀要（保留英文專業術語）
3. 提取所有 action items + 負責人 + deadline
4. 標記決議事項
5. 識別風險點

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
                  client_name: str = "", project_name: str = "") -> dict:
    """
    一個 Gemini call 完成：transcribe + summarize
    < 18MB 用 inline，>= 18MB 用 Files API upload
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

    prompt = SUMMARY_PROMPT.format(
        duration="（請根據錄音實際長度填寫）",
        client_info=client_info,
    )

    # === 小檔案：inline data（最快） ===
    if len(audio_bytes) <= INLINE_MAX_BYTES:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                prompt,
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
            ),
        )
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

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, audio_file],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
            ),
        )

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
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=TRANSLATE_PROMPT.format(
            target_name=target_name,
            summary=summary_md,
        ),
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=8192,
        ),
    )
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
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=SENTIMENT_PROMPT.format(summary=summary_md),
        config=types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=4096,
        ),
    )
    return response.text
