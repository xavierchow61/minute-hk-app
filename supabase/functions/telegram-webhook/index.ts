// Telegram Bot webhook handler — Session 3 + menu
//
// 用戶 send voice → bot reply inline keyboard 問「📝 完整摘要 / 📋 純轉文字」
// 用戶 tap → callback_query → 對應 pipeline 處理。
//
// Commands:
//   /start <code>  → link Telegram chat to Minute.hk account
//   /help          → 命令清單
//   /quota         → 顯示今日 + 本月 usage
//   voice / audio  → 出 inline menu 問 mode
//
// Required Edge Function secrets:
//   TELEGRAM_BOT_TOKEN     — from @BotFather
//   GEMINI_API_KEY         — same key as web app

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.4";

const TELEGRAM_BOT_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN")!;
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const GEMINI_API_KEY = Deno.env.get("GEMINI_API_KEY")!;

const GEMINI_MODEL = "gemini-2.5-pro";  // Flash family 全線 overload 緊, pro quota 鬆 + 質素更高
const TG_API = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}`;
const TG_FILE_API = `https://api.telegram.org/file/bot${TELEGRAM_BOT_TOKEN}`;
const GEMINI_URL =
  `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}`;

const APP_URL = "https://minute-hk-app-uat.streamlit.app";
const MAX_AUDIO_SECONDS = 300;

const FREE_MONTHLY = 6000, FREE_DAILY = 900;
const PRO_MONTHLY = 12000, PRO_DAILY = 1800;

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

// ============================================================
// Prompts
// ============================================================
const INDUSTRY_PROMPTS: Record<string, string> = {
  generic: "你係資深嘅商務會議秘書。",
  accounting:
    "你係香港資深會計師樓嘅高級秘書，熟悉會計、審計、稅務、財務報表術語。識別會議中嘅會計議題（IFRS、HKFRS、profit tax、audit、disclosure 等）。",
  legal: "你係香港律師樓嘅 paralegal，熟悉合約、訴訟、合規術語。",
  medical: "你係醫療專業秘書，熟悉診斷、處方、病歷術語。",
  sales: "你係銷售團隊嘅 admin，熟悉 pipeline、deal、quota、commission 術語。",
  education: "你係教育機構嘅 admin，熟悉課程、學生表現、家校溝通術語。",
  real_estate: "你係地產業 admin，熟悉樓盤、租務、按揭、估價術語。",
  finance: "你係金融機構秘書，熟悉投資、風險、合規、產品術語。",
  consulting: "你係顧問公司 PA，熟悉 strategy、deliverable、stakeholder 術語。",
  tech: "你係科技公司 PM 助手，熟悉 product、sprint、roadmap、metrics 術語。",
};

function buildSummaryPrompt(durationSec: number, industry: string, jargon: string, companyName: string): string {
  const system = INDUSTRY_PROMPTS[industry] || INDUSTRY_PROMPTS.generic;
  const durationStr = `${durationSec} 秒（${(durationSec / 60).toFixed(1)} 分鐘）`;
  let context = "";
  if (companyName) context += `\n你嘅僱主公司：${companyName}。`;
  if (jargon) context += `\n你公司常用嘅特殊術語/人名：${jargon}（識別錄音時請特別留意）。`;

  return `${system}${context}

呢段係一段會議錄音（廣東話 / 普通話 / 英文夾雜）。

【⚠️ 錄音質量檢查】幾乎全靜音 → 返回「# ⚠️ 錄音質量問題」+ 提示重錄。
【🛑 禁止】唔可以重複字符、唔可以 hallucinate。

請用以下 Markdown 格式輸出：

# 📝 會議紀要

## 📅 基本資訊
- **錄音時長**：${durationStr}
- **來源**：Telegram voice message

## 👥 與會者
（每位用 \`講者 A / B / C\` 標籤 + 角色推斷）

## 🎯 會議重點
（3-5 句 executive summary）

## 💡 主要討論議題
1. **[議題]** — 邊位講者講咩 (用 講者 A/B)

## ✅ 決議事項
- ...

## 📋 Action Items
| # | 待辦事項 | 負責人（講者 X） | Deadline | 優先級 |
|---|---------|------------------|----------|--------|
| 1 | ... | 講者 A | ... | 🔴高/🟡中/🟢低 |

## ⚠️ 風險與跟進
- ...

---
*由 Minute.hk AI 自動生成 (via Telegram)*`;
}

const TRANSCRIBE_PROMPT = `請將呢段錄音逐字 transcribe，**必須做 speaker diarization**。

# ✅ 輸出格式（嚴格）

\`\`\`
**👥 與會者**: 講者 A、講者 B（共 2 位）

**講者 A** [00:00]: Hello,大家好。

**講者 B** [00:08]: Hello。
\`\`\`

# 規則
1. 講者 label 必須係 \`**講者 A**\` (繁中 + 粗體) — 唔好用 \`A:\` 短 form
2. 每 turn 獨立一段，空行分隔
3. 第一行係 \`**👥 與會者**: 講者 X、Y（共 N 位）\`
4. 時間戳 optional
5. 繁體中文、保留原話、保留粵語口語、聽唔清用 \`[聽唔清]\`

# 禁止
- 唔好總結 / 加 markdown headings
- 唔好用短 form \`A:\``;

// ============================================================
// Telegram helpers
// ============================================================
async function sendMessage(chatId: number | string, text: string): Promise<void> {
  const MAX = 4000;
  const chunks: string[] = [];
  let remaining = text;
  while (remaining.length > MAX) {
    const splitAt = remaining.lastIndexOf("\n", MAX);
    const breakPoint = splitAt > MAX / 2 ? splitAt : MAX;
    chunks.push(remaining.substring(0, breakPoint));
    remaining = remaining.substring(breakPoint).trimStart();
  }
  if (remaining) chunks.push(remaining);

  for (let i = 0; i < chunks.length; i++) {
    const prefix = chunks.length > 1 ? `📄 (${i + 1}/${chunks.length}) ` : "";
    try {
      await fetch(`${TG_API}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_id: chatId,
          text: prefix + chunks[i],
          disable_web_page_preview: true,
        }),
      });
    } catch (e) {
      console.error("sendMessage failed:", e);
    }
  }
}

async function sendMessageWithKeyboard(
  chatId: number | string,
  text: string,
  keyboard: Array<Array<{ text: string; callback_data: string }>>,
): Promise<void> {
  try {
    await fetch(`${TG_API}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        reply_markup: { inline_keyboard: keyboard },
      }),
    });
  } catch (e) {
    console.error("sendMessageWithKeyboard failed:", e);
  }
}

async function answerCallbackQuery(callbackQueryId: string, text?: string): Promise<void> {
  try {
    await fetch(`${TG_API}/answerCallbackQuery`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        callback_query_id: callbackQueryId,
        text: text || "",
      }),
    });
  } catch (_e) { /* non-critical */ }
}

async function editMessageReplyMarkup(
  chatId: number | string,
  messageId: number,
  keyboard: Array<Array<{ text: string; callback_data: string }>> | null,
): Promise<void> {
  try {
    await fetch(`${TG_API}/editMessageReplyMarkup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        message_id: messageId,
        reply_markup: keyboard ? { inline_keyboard: keyboard } : { inline_keyboard: [] },
      }),
    });
  } catch (_e) { /* non-critical */ }
}

async function sendChatAction(chatId: number | string, action: string): Promise<void> {
  try {
    await fetch(`${TG_API}/sendChatAction`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, action }),
    });
  } catch (_e) { /* non-critical */ }
}

async function downloadTelegramFile(fileId: string): Promise<{ bytes: Uint8Array; mimeType: string } | null> {
  const infoRes = await fetch(`${TG_API}/getFile?file_id=${encodeURIComponent(fileId)}`);
  if (!infoRes.ok) return null;
  const info = await infoRes.json();
  if (!info.ok) return null;
  const filePath: string = info.result.file_path;
  const binRes = await fetch(`${TG_FILE_API}/${filePath}`);
  if (!binRes.ok) return null;
  const bytes = new Uint8Array(await binRes.arrayBuffer());
  const ext = filePath.split(".").pop()?.toLowerCase() || "";
  const mimeMap: Record<string, string> = {
    ogg: "audio/ogg", oga: "audio/ogg", mp3: "audio/mpeg",
    m4a: "audio/mp4", wav: "audio/wav", webm: "audio/webm", mp4: "video/mp4",
  };
  return { bytes, mimeType: mimeMap[ext] || "audio/ogg" };
}

function uint8ToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + chunkSize)));
  }
  return btoa(binary);
}

async function callGemini(audioBytes: Uint8Array, mimeType: string, prompt: string, maxTokens: number): Promise<string> {
  console.log("callGemini using model:", GEMINI_MODEL);
  const b64 = uint8ToBase64(audioBytes);
  const res = await fetch(GEMINI_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }, { inlineData: { mimeType, data: b64 } }] }],
      generationConfig: { temperature: 0.2, maxOutputTokens: maxTokens },
    }),
  });
  if (!res.ok) throw new Error(`Gemini ${res.status} (model=${GEMINI_MODEL}): ${(await res.text()).substring(0, 300)}`);
  const data = await res.json();
  return data?.candidates?.[0]?.content?.parts?.[0]?.text || "";
}

function stripMarkdown(text: string): string {
  let t = text || "";
  t = t.replace(/^#{1,6}\s*(.+?)\s*$/gm, "━━ $1 ━━");
  t = t.replace(/\*\*(.+?)\*\*/g, "$1");
  t = t.replace(/(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)/g, "$1");
  t = t.replace(/`([^`\n]+)`/g, "「$1」");
  t = t.replace(/^[\-\*]\s+/gm, "• ");
  t = t.replace(/^[\-=]{3,}$/gm, "");
  t = t.replace(/\n{3,}/g, "\n\n");
  return t.trim();
}

function normalizeDiarization(text: string): string {
  if (!text) return "";
  const pattern = /(?:^|(?<=[\s。！？.!?,\n]))(?:\*\*)?(?:Speaker\s+|Person\s+|講者\s*)?([A-Z])(?:\*\*)?[:：]\s*/g;
  const matches: Array<{ index: number; length: number; speaker: string }> = [];
  let m: RegExpExecArray | null;
  while ((m = pattern.exec(text)) !== null) {
    matches.push({ index: m.index, length: m[0].length, speaker: m[1] });
    if (m[0].length === 0) pattern.lastIndex++;
  }
  if (matches.length === 0) return text.trim();
  const lines: string[] = [];
  const pre = text.substring(0, matches[0].index).trim();
  if (pre && !pre.startsWith("**👥")) lines.push(pre);
  for (let i = 0; i < matches.length; i++) {
    const contentStart = matches[i].index + matches[i].length;
    const contentEnd = i + 1 < matches.length ? matches[i + 1].index : text.length;
    const content = text.substring(contentStart, contentEnd).trim();
    if (content) lines.push(`**講者 ${matches[i].speaker}**: ${content}`);
  }
  let body = lines.join("\n\n");
  const speakers = new Set<string>();
  const speakerRe = /\*\*講者\s+([A-Z])\*\*/g;
  let sm: RegExpExecArray | null;
  while ((sm = speakerRe.exec(body)) !== null) speakers.add(sm[1]);
  const sortedSpeakers = Array.from(speakers).sort();
  if (sortedSpeakers.length > 0 && !body.includes("**👥 與會者**")) {
    const header = `**👥 與會者**: ${sortedSpeakers.map((s) => `講者 ${s}`).join("、")}（共 ${sortedSpeakers.length} 位）`;
    body = header + "\n\n" + body;
  }
  return body.trim();
}

// ============================================================
// User lookup + quota
// ============================================================
async function lookupUserByChat(chatId: number): Promise<{
  user_id: string; plan: string; industry: string; jargon: string; company_name: string;
} | null> {
  const { data } = await supabase
    .from("user_plans")
    .select("user_id, plan, industry, jargon, company_name")
    .eq("telegram_chat_id", String(chatId))
    .maybeSingle();
  if (!data) return null;
  return {
    user_id: data.user_id,
    plan: data.plan || "free",
    industry: data.industry || "generic",
    jargon: data.jargon || "",
    company_name: data.company_name || "",
  };
}

async function getUsageStats(userId: string): Promise<{ daily: number; monthly: number }> {
  const now = new Date();
  const dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
  const [dailyRes, monthlyRes] = await Promise.all([
    supabase.from("meetings").select("duration_seconds").eq("user_id", userId).gte("created_at", dayStart.toISOString()),
    supabase.from("meetings").select("duration_seconds").eq("user_id", userId).gte("created_at", monthStart.toISOString()),
  ]);
  const daily = (dailyRes.data || []).reduce((s, m) => s + (m.duration_seconds || 0), 0);
  const monthly = (monthlyRes.data || []).reduce((s, m) => s + (m.duration_seconds || 0), 0);
  return { daily, monthly };
}

// ============================================================
// Voice processing (called after user picks mode)
// ============================================================
async function processSummary(
  chatId: number,
  fileId: string,
  durationSec: number,
  kind: "voice" | "audio",
  userInfo: { user_id: string; industry: string; jargon: string; company_name: string },
): Promise<void> {
  await sendMessage(chatId, `⏳ AI 生成完整會議紀要中...（${durationSec}s 錄音通常 ${Math.max(20, Math.ceil(durationSec * 0.6))}s）`);
  sendChatAction(chatId, "typing");

  const dl = await downloadTelegramFile(fileId);
  if (!dl) {
    await sendMessage(chatId, "❌ 下載錄音失敗。可能過咗期，請重新 send。");
    return;
  }

  const prompt = buildSummaryPrompt(durationSec, userInfo.industry, userInfo.jargon, userInfo.company_name);
  let summary: string;
  try {
    summary = await callGemini(dl.bytes, dl.mimeType, prompt, 16384);
  } catch (e) {
    console.error("Gemini summary error:", e);
    await sendMessage(chatId, `❌ AI 處理失敗：${String(e).substring(0, 200)}`);
    return;
  }
  if (!summary || summary.trim().length < 20) {
    await sendMessage(chatId, "❌ AI 收唔到內容。可能錄音太靜 / 太短，請重錄。");
    return;
  }

  const ext = kind === "audio" ? "mp3" : "ogg";
  const { error: insErr } = await supabase.from("meetings").insert({
    user_id: userInfo.user_id,
    summary,
    transcript: "",
    client: null,
    project: "Telegram",
    duration_seconds: durationSec,
    audio_filename: `telegram-${kind}-${Date.now()}.${ext}`,
  });
  if (insErr) {
    console.error("Meetings insert failed (summary path):", JSON.stringify(insErr));
  } else {
    console.log("Meetings insert OK (summary path), user_id:", userInfo.user_id);
  }

  await sendMessage(chatId, stripMarkdown(summary));
  await sendMessage(chatId, `🔗 完整功能（翻譯 / 語氣分析 / 下載 Word/PDF）：\n${APP_URL}`);
}

async function processTranscribe(
  chatId: number,
  fileId: string,
  durationSec: number,
  kind: "voice" | "audio",
  userInfo: { user_id: string },
): Promise<void> {
  await sendMessage(chatId, `⏳ 純轉文字 + 講者識別中...（${durationSec}s 錄音通常 ${Math.max(20, Math.ceil(durationSec * 0.5))}s）`);
  sendChatAction(chatId, "typing");

  const dl = await downloadTelegramFile(fileId);
  if (!dl) {
    await sendMessage(chatId, "❌ 下載錄音失敗。可能過咗期，請重新 send。");
    return;
  }

  let transcript: string;
  try {
    transcript = await callGemini(dl.bytes, dl.mimeType, TRANSCRIBE_PROMPT, 32768);
  } catch (e) {
    console.error("Gemini transcribe error:", e);
    await sendMessage(chatId, `❌ AI 處理失敗：${String(e).substring(0, 200)}`);
    return;
  }
  if (!transcript || transcript.trim().length < 5) {
    await sendMessage(chatId, "❌ AI 收唔到內容。可能錄音太靜 / 太短。");
    return;
  }

  const normalized = normalizeDiarization(transcript);
  const summaryWrap = `# 📋 純文字稿\n\n**來源**: Telegram ${kind}（${durationSec}s）\n\n---\n\n${normalized}`;
  const ext = kind === "audio" ? "mp3" : "ogg";
  const { error: insErr } = await supabase.from("meetings").insert({
    user_id: userInfo.user_id,
    summary: summaryWrap,
    transcript: normalized,
    client: null,
    project: "Telegram",
    duration_seconds: durationSec,
    audio_filename: `telegram-${kind}-${Date.now()}.${ext}`,
  });
  if (insErr) {
    console.error("Meetings insert failed (transcribe path):", JSON.stringify(insErr));
  } else {
    console.log("Meetings insert OK (transcribe path), user_id:", userInfo.user_id);
  }

  await sendMessage(chatId, "✅ 轉錄完成：\n\n" + stripMarkdown(normalized));
  await sendMessage(chatId, `🔗 用 AI 整理紀要 / 翻譯 / 下載：\n${APP_URL}`);
}

// ============================================================
// Handlers (commands + voice + callback)
// ============================================================
async function handleStartCommand(chatId: number, text: string): Promise<void> {
  const parts = text.trim().split(/\s+/);
  if (parts.length < 2) {
    await sendMessage(
      chatId,
      `👋 Hello! 我係 Minute.hk Bot。\n\n請先入 ${APP_URL} → ⚙️ 設定 → 🔗 連接 Telegram，跟住 click 個 link 返呢度。`,
    );
    return;
  }
  const code = parts[1].trim().toUpperCase();
  const { data: linkRow } = await supabase
    .from("telegram_link_codes").select("user_id, expires_at, used_at").eq("code", code).maybeSingle();
  if (!linkRow) { await sendMessage(chatId, `❌ 連接碼 \`${code}\` 無效。`); return; }
  if (linkRow.used_at) { await sendMessage(chatId, "❌ 呢個連接碼已被使用過。"); return; }
  if (new Date(linkRow.expires_at) < new Date()) { await sendMessage(chatId, "❌ 連接碼已過期。"); return; }

  await supabase.from("user_plans").update({ telegram_chat_id: String(chatId) }).eq("user_id", linkRow.user_id);
  await supabase.from("telegram_link_codes").update({ used_at: new Date().toISOString() }).eq("code", code);

  await sendMessage(
    chatId,
    `🎉 連接成功！\n\n而家可以：\n• Send voice / audio → 揀「📝 完整摘要」或「📋 純轉文字」\n• /quota — 睇 usage\n• /help — 命令清單\n\n返 ${APP_URL} refresh 設定見 Connected ✓。`,
  );
}

async function handleQuotaCommand(chatId: number): Promise<void> {
  const userInfo = await lookupUserByChat(chatId);
  if (!userInfo) {
    await sendMessage(chatId, `❌ 你 Telegram 未連接 Minute.hk account。\n\n去 ${APP_URL} → ⚙️ 設定 → 連接 Telegram。`);
    return;
  }
  const { daily, monthly } = await getUsageStats(userInfo.user_id);
  const dailyLimit = userInfo.plan === "pro" || userInfo.plan === "team" ? PRO_DAILY : FREE_DAILY;
  const monthlyLimit = userInfo.plan === "pro" || userInfo.plan === "team" ? PRO_MONTHLY : FREE_MONTHLY;
  const planEmoji = userInfo.plan === "pro" ? "⭐" : userInfo.plan === "team" ? "👥" : "🆓";
  await sendMessage(
    chatId,
    `📊 你嘅 quota (${planEmoji} ${userInfo.plan.toUpperCase()}):\n\n` +
      `📅 今日: ${(daily / 60).toFixed(1)} / ${(dailyLimit / 60).toFixed(0)} 分鐘\n` +
      `📆 本月: ${(monthly / 60).toFixed(1)} / ${(monthlyLimit / 60).toFixed(0)} 分鐘`,
  );
}

async function handleHelpCommand(chatId: number): Promise<void> {
  await sendMessage(
    chatId,
    `ℹ️ Minute.hk Bot — 命令：\n\n` +
      `/start <code> — 連接 Minute.hk account\n` +
      `/quota — 睇今日 + 本月 usage\n` +
      `/help — 呢個訊息\n\n` +
      `📢 直接 send voice / audio file，bot 會問你揀：\n` +
      `  • 📝 完整摘要 — AI 整理紀要 (與會者 / Action Items / 風險)\n` +
      `  • 📋 純轉文字 — 逐字稿 + 講者識別`,
  );
}

async function handleVoice(
  chatId: number,
  mediaObj: { file_id: string; duration?: number; mime_type?: string },
  kind: "voice" | "audio",
): Promise<void> {
  const userInfo = await lookupUserByChat(chatId);
  if (!userInfo) {
    await sendMessage(chatId, `❌ 你 Telegram 未連接 Minute.hk account。\n\n去 ${APP_URL} → ⚙️ 設定 → 連接 Telegram。`);
    return;
  }
  const durationSec = mediaObj.duration || 0;
  if (durationSec > MAX_AUDIO_SECONDS) {
    await sendMessage(chatId, `❌ 錄音太長（${durationSec}s，上限 ${MAX_AUDIO_SECONDS}s）。\n\n長錄音請用 web app：${APP_URL}`);
    return;
  }
  const dailyLimit = userInfo.plan === "pro" || userInfo.plan === "team" ? PRO_DAILY : FREE_DAILY;
  const monthlyLimit = userInfo.plan === "pro" || userInfo.plan === "team" ? PRO_MONTHLY : FREE_MONTHLY;
  const { daily, monthly } = await getUsageStats(userInfo.user_id);
  if (durationSec > dailyLimit - daily) {
    await sendMessage(chatId, `❌ 超過今日 quota。\n用咗 ${(daily / 60).toFixed(1)} / ${(dailyLimit / 60).toFixed(0)} 分鐘。`);
    return;
  }
  if (durationSec > monthlyLimit - monthly) {
    await sendMessage(chatId, `❌ 超過本月 quota。\n用咗 ${(monthly / 60).toFixed(1)} / ${(monthlyLimit / 60).toFixed(0)} 分鐘。`);
    return;
  }

  // Save pending + show menu
  const expiresAt = new Date(Date.now() + 10 * 60 * 1000).toISOString();
  const { data: pending, error: pendingErr } = await supabase
    .from("telegram_pending_voice")
    .insert({
      chat_id: String(chatId),
      user_id: userInfo.user_id,
      file_id: mediaObj.file_id,
      duration_sec: durationSec,
      kind,
      expires_at: expiresAt,
    })
    .select("id")
    .single();

  if (pendingErr || !pending) {
    console.error("save pending failed:", pendingErr);
    await sendMessage(chatId, "❌ 系統錯誤，請稍後再試。");
    return;
  }

  await sendMessageWithKeyboard(
    chatId,
    `🎙️ 收到 ${durationSec} 秒錄音。點處理？\n\n📝 完整摘要 = AI 整理紀要（與會者 / Action Items / 風險）\n📋 純轉文字 = 逐字稿 + 講者識別`,
    [[
      { text: "📝 完整摘要", callback_data: `s:${pending.id}` },
      { text: "📋 純轉文字", callback_data: `t:${pending.id}` },
    ]],
  );
}

async function handleCallbackQuery(callbackQuery: any): Promise<void> {
  const chatId = callbackQuery.message?.chat?.id;
  const messageId = callbackQuery.message?.message_id;
  const data: string = callbackQuery.data || "";

  // Always answer to remove loading state
  await answerCallbackQuery(callbackQuery.id);

  if (!chatId) return;

  // Parse "s:42" / "t:42"
  const match = data.match(/^([st]):(\d+)$/);
  if (!match) {
    await sendMessage(chatId, "❌ 唔識呢個 button 嘅 callback。");
    return;
  }
  const mode = match[1]; // s | t
  const pendingId = parseInt(match[2], 10);

  // Lookup pending
  const { data: pending } = await supabase
    .from("telegram_pending_voice")
    .select("user_id, file_id, duration_sec, kind, expires_at")
    .eq("id", pendingId)
    .maybeSingle();

  // Remove the inline keyboard from the original message (UX cleanup)
  if (messageId) {
    await editMessageReplyMarkup(chatId, messageId, []);
  }

  if (!pending) {
    await sendMessage(chatId, "❌ 揾唔到呢條錄音，可能已 process 過 / 過期。請重新 send voice。");
    return;
  }
  if (new Date(pending.expires_at) < new Date()) {
    await sendMessage(chatId, "❌ 錄音已過期（10 分鐘），請重新 send。");
    await supabase.from("telegram_pending_voice").delete().eq("id", pendingId);
    return;
  }

  // Lookup user for processing
  const userInfo = await lookupUserByChat(chatId);
  if (!userInfo) {
    await sendMessage(chatId, "❌ 你 Telegram 已斷開連接。請重新連接。");
    return;
  }

  // Dispatch
  if (mode === "s") {
    await processSummary(chatId, pending.file_id, pending.duration_sec, pending.kind as "voice" | "audio", userInfo);
  } else {
    await processTranscribe(chatId, pending.file_id, pending.duration_sec, pending.kind as "voice" | "audio", userInfo);
  }

  // Delete pending (success)
  await supabase.from("telegram_pending_voice").delete().eq("id", pendingId);
}

// ============================================================
// Main Deno serve handler
// ============================================================
Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return new Response("ok");

  let update: any;
  try {
    update = await req.json();
  } catch (_e) {
    return new Response("invalid json", { status: 400 });
  }

  console.log("Update:", JSON.stringify(update).substring(0, 500));

  // Callback query (user tap inline keyboard button)
  if (update.callback_query) {
    try { await handleCallbackQuery(update.callback_query); }
    catch (e) { console.error("Callback error:", e); }
    return new Response("ok");
  }

  const msg = update.message || update.edited_message;
  if (!msg?.chat?.id) return new Response("ok");

  const chatId: number = msg.chat.id;
  const text: string = msg.text || msg.caption || "";

  try {
    if (text.startsWith("/start")) {
      await handleStartCommand(chatId, text);
    } else if (text === "/help") {
      await handleHelpCommand(chatId);
    } else if (text === "/quota") {
      await handleQuotaCommand(chatId);
    } else if (msg.voice) {
      await handleVoice(chatId, msg.voice, "voice");
    } else if (msg.audio) {
      await handleVoice(chatId, msg.audio, "audio");
    } else {
      await sendMessage(chatId, `👋 Hi! Send /help 睇命令，或者直接 send voice message。`);
    }
  } catch (e) {
    console.error("Handler error:", e);
  }

  return new Response("ok");
});
