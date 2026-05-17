"""Gemini transcribe + summarize for cloud (one API does both)"""
import streamlit as st
from google import genai
from google.genai import types

GEMINI_MODEL = "gemini-2.5-flash"


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


def process_audio(audio_bytes: bytes, mime_type: str,
                  client_name: str = "", project_name: str = "") -> dict:
    """
    一個 Gemini call 完成：transcribe + summarize
    Returns: {summary: str, transcript: str (optional)}
    """
    client = _client()

    # Upload audio file to Gemini
    audio_file = client.files.upload(
        file=audio_bytes,
        config=types.UploadFileConfig(mime_type=mime_type),
    )

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

    # Generate summary from audio
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[prompt, audio_file],
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=8192,
        ),
    )

    # Clean up uploaded file
    try:
        client.files.delete(name=audio_file.name)
    except Exception:
        pass

    return {
        "summary": response.text,
        "model": GEMINI_MODEL,
    }


def get_transcript(audio_bytes: bytes, mime_type: str) -> str:
    """單獨攞文字稿（如有需要）"""
    client = _client()
    audio_file = client.files.upload(
        file=audio_bytes,
        config=types.UploadFileConfig(mime_type=mime_type),
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            "請將呢段錄音逐字 transcribe 出嚟。保留原文嘅語言（廣東話、普通話、英文）。"
            "格式：純文字，唔需要 timestamp。",
            audio_file,
        ],
        config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=8192),
    )
    try:
        client.files.delete(name=audio_file.name)
    except Exception:
        pass
    return response.text
