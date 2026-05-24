// Telegram Bot webhook handler — Session 2: real transcription via Gemini
//
// Receives Telegram updates. Handles:
//   /start <code>  → link Telegram chat to Minute.hk account
//   voice / audio  → download + Gemini transcribe (with diarization) + save +
//                    reply transcript + link to web app
//   other          → friendly hint
//
// Required secrets (Supabase Dashboard → Edge Functions → Secrets):
//   TELEGRAM_BOT_TOKEN     — from @BotFather
//   GEMINI_API_KEY         — same key as web app uses (Streamlit secrets)
//   (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY auto-provided)
//
// Limits:
//   - Audio max duration: 300 seconds (5 min). Longer → suggest web app.
//   - Telegram bot file download: 20 MB Telegram-side hard limit.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.4";

const TELEGRAM_BOT_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN")!;
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const GEMINI_API_KEY = Deno.env.get("GEMINI_API_KEY")!;

const GEMINI_MODEL = "gemini-2.5-flash";
const TG_API = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}`;
const TG_FILE_API = `https://api.telegram.org/file/bot${TELEGRAM_BOT_TOKEN}`;
const GEMINI_URL =
  `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}`;

const APP_URL = "https://minute-hk-app-uat.streamlit.app";
const MAX_AUDIO_SECONDS = 300; // 5-min cap for Edge Function safety

// Quota (must match db.py constants)
const FREE_MONTHLY = 6000;
const FREE_DAILY = 900;
const PRO_MONTHLY = 12000;
const PRO_DAILY = 1800;

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

// ============================================================
// Gemini prompt — same as web app's TRANSCRIBE_ONLY_PROMPT
// ============================================================
const TRANSCRIBE_PROMPT = `請將呢段錄音逐字 transcribe 成文字稿，**必須做 speaker diarization (識別講者)**。

# ✅ 唯一可接受嘅輸出格式（嚴格跟）

\`\`\`
**👥 與會者**: 講者 A、講者 B（共 2 位）

**講者 A** [00:00]: Hello,大家好。

**講者 B** [00:08]: Hello。
\`\`\`

# 規則

1. 講者 label 必須係完整 \`**講者 A**\` / \`**講者 B**\` ... (繁中「講者」+ 大階英文字母 + markdown 粗體)
2. 每個 turn 必須係獨立一段，turn 之間用空行（雙換行）分隔
3. 唔好用短 form 例如 \`A:\` 或 \`Speaker A\`
4. 第一行永遠係 \`**👥 與會者**: 講者 A、講者 B、...（共 N 位）\`
5. 時間戳 \`[mm:ss]\` 識別到先加（optional）

# 講者識別
- 根據聲線、語氣判斷
- 單人錄音都要用 \`講者 A\` label
- 同一人連續講都係同一個 label

# 轉錄要求
1. 繁體中文（簡體 → 繁體）
2. 保留原話、唔總結、唔修飾
3. 中英夾雜照保留
4. 粵語口語照保留
5. 聽唔清用 \`[聽唔清]\` 標記

# 禁止
- 唔好總結 / 加 markdown headings
- 唔好用 \`A:\` 短 form
- 唔好將多個講者擠喺同一段`;

// ============================================================
// Helpers
// ============================================================

async function sendMessage(chatId: number | string, text: string): Promise<void> {
  // Telegram limit 4096 chars; chunk if needed
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

async function sendChatAction(
  chatId: number | string,
  action: string,
): Promise<void> {
  try {
    await fetch(`${TG_API}/sendChatAction`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, action }),
    });
  } catch (_e) { /* non-critical */ }
}

async function downloadTelegramFile(fileId: string): Promise<{ bytes: Uint8Array; mimeType: string } | null> {
  // Step 1: getFile to obtain file_path
  const infoRes = await fetch(`${TG_API}/getFile?file_id=${encodeURIComponent(fileId)}`);
  if (!infoRes.ok) {
    console.error("getFile failed:", await infoRes.text());
    return null;
  }
  const info = await infoRes.json();
  if (!info.ok) {
    console.error("getFile not ok:", info);
    return null;
  }
  const filePath: string = info.result.file_path;

  // Step 2: download binary
  const binRes = await fetch(`${TG_FILE_API}/${filePath}`);
  if (!binRes.ok) {
    console.error("file download failed:", binRes.status);
    return null;
  }
  const bytes = new Uint8Array(await binRes.arrayBuffer());
  // Telegram OGG = audio/ogg; mp3/m4a follow ext
  const ext = filePath.split(".").pop()?.toLowerCase() || "";
  const mimeMap: Record<string, string> = {
    ogg: "audio/ogg",
    oga: "audio/ogg",
    mp3: "audio/mpeg",
    m4a: "audio/mp4",
    wav: "audio/wav",
    webm: "audio/webm",
    mp4: "video/mp4",
  };
  return { bytes, mimeType: mimeMap[ext] || "audio/ogg" };
}

function uint8ToBase64(bytes: Uint8Array): string {
  // 高效 base64 encode (避免 String.fromCharCode 大量 spread 嘅 stack overflow)
  let binary = "";
  const chunkSize = 0x8000; // 32KB
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode.apply(
      null,
      Array.from(bytes.subarray(i, i + chunkSize)),
    );
  }
  return btoa(binary);
}

async function transcribeWithGemini(
  audioBytes: Uint8Array,
  mimeType: string,
): Promise<string> {
  const b64 = uint8ToBase64(audioBytes);
  const res = await fetch(GEMINI_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{
        parts: [
          { text: TRANSCRIBE_PROMPT },
          { inlineData: { mimeType, data: b64 } },
        ],
      }],
      generationConfig: {
        temperature: 0.1,
        maxOutputTokens: 32768,
      },
    }),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Gemini API ${res.status}: ${errText.substring(0, 300)}`);
  }

  const data = await res.json();
  const text: string | undefined =
    data?.candidates?.[0]?.content?.parts?.[0]?.text;
  return text || "";
}

// ============================================================
// Normalize diarization output (port from Python _normalize_diarization)
// ============================================================
function normalizeDiarization(text: string): string {
  if (!text) return "";

  // 揾全部 speaker labels（包 short form 如 "A:" 或 canonical "**講者 A**:"）
  // JS regex lookbehind support varies; use global flag + manual iteration.
  const labelPattern =
    /(?:^|(?<=[\s。！？.!?,\n]))(?:\*\*)?(?:Speaker\s+|Person\s+|講者\s*)?([A-Z])(?:\*\*)?[:：]\s*/g;

  const matches: Array<{ index: number; length: number; speaker: string }> = [];
  let m: RegExpExecArray | null;
  while ((m = labelPattern.exec(text)) !== null) {
    matches.push({ index: m.index, length: m[0].length, speaker: m[1] });
    if (m[0].length === 0) labelPattern.lastIndex++;
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

  // Prepend 與會者 header
  const speakers = new Set<string>();
  const speakerRe = /\*\*講者\s+([A-Z])\*\*/g;
  let sm: RegExpExecArray | null;
  while ((sm = speakerRe.exec(body)) !== null) speakers.add(sm[1]);
  const sortedSpeakers = Array.from(speakers).sort();
  if (sortedSpeakers.length > 0 && !body.includes("**👥 與會者**")) {
    const header = `**👥 與會者**: ${
      sortedSpeakers.map((s) => `講者 ${s}`).join("、")
    }（共 ${sortedSpeakers.length} 位）`;
    body = header + "\n\n" + body;
  }

  return body.trim();
}

// Strip markdown for Telegram-friendly plain text
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

// ============================================================
// Usage helpers
// ============================================================
async function getUsageStats(userId: string): Promise<{ daily: number; monthly: number }> {
  const now = new Date();
  const dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);

  const [dailyRes, monthlyRes] = await Promise.all([
    supabase
      .from("meetings")
      .select("duration_seconds")
      .eq("user_id", userId)
      .gte("created_at", dayStart.toISOString()),
    supabase
      .from("meetings")
      .select("duration_seconds")
      .eq("user_id", userId)
      .gte("created_at", monthStart.toISOString()),
  ]);

  const daily = (dailyRes.data || []).reduce(
    (sum, m) => sum + (m.duration_seconds || 0),
    0,
  );
  const monthly = (monthlyRes.data || []).reduce(
    (sum, m) => sum + (m.duration_seconds || 0),
    0,
  );
  return { daily, monthly };
}

// ============================================================
// Handlers
// ============================================================
async function handleStartCommand(chatId: number, text: string): Promise<void> {
  const parts = text.trim().split(/\s+/);
  if (parts.length < 2) {
    await sendMessage(
      chatId,
      `👋 Hello! 我係 Minute.hk Bot。\n\n` +
        `請先入 ${APP_URL} → ⚙️ 設定 → 🔗 連接 Telegram，` +
        `跟住 click 個 link 返呢度。`,
    );
    return;
  }

  const code = parts[1].trim().toUpperCase();
  const { data: linkRow } = await supabase
    .from("telegram_link_codes")
    .select("user_id, expires_at, used_at")
    .eq("code", code)
    .maybeSingle();

  if (!linkRow) {
    await sendMessage(chatId, `❌ 連接碼 \`${code}\` 無效。請重新生成。`);
    return;
  }
  if (linkRow.used_at) {
    await sendMessage(chatId, "❌ 呢個連接碼已被使用過。請重新生成。");
    return;
  }
  if (new Date(linkRow.expires_at) < new Date()) {
    await sendMessage(chatId, "❌ 連接碼已過期（10 分鐘有效）。請重新生成。");
    return;
  }

  const { error: updErr } = await supabase
    .from("user_plans")
    .update({ telegram_chat_id: String(chatId) })
    .eq("user_id", linkRow.user_id);
  if (updErr) {
    console.error("update user_plans failed:", updErr);
    await sendMessage(chatId, "❌ 系統錯誤，請稍後再試。");
    return;
  }

  await supabase
    .from("telegram_link_codes")
    .update({ used_at: new Date().toISOString() })
    .eq("code", code);

  await sendMessage(
    chatId,
    `🎉 連接成功！\n\n` +
      `而家可以：\n` +
      `1. 直接 send voice message → 自動 transcribe + 識別講者\n` +
      `2. 喺 web app 處理錄音 → 撳「📤 Send 落 Telegram」推 summary\n\n` +
      `返 ${APP_URL} refresh 設定見到 Connected ✓。`,
  );
}

async function handleVoice(
  chatId: number,
  mediaObj: { file_id: string; duration?: number; mime_type?: string },
  kind: "voice" | "audio",
): Promise<void> {
  // 1. Look up linked user
  const { data: userPlan } = await supabase
    .from("user_plans")
    .select("user_id, plan")
    .eq("telegram_chat_id", String(chatId))
    .maybeSingle();

  if (!userPlan) {
    await sendMessage(
      chatId,
      `❌ 你 Telegram 未連接 Minute.hk account。\n\n` +
        `請去 ${APP_URL} → ⚙️ 設定 → 🔗 連接 Telegram。`,
    );
    return;
  }

  const userId: string = userPlan.user_id;
  const plan: string = userPlan.plan || "free";
  const durationSec = mediaObj.duration || 0;

  // 2. Length cap (Edge Function 安全)
  if (durationSec > MAX_AUDIO_SECONDS) {
    await sendMessage(
      chatId,
      `❌ 錄音太長（${durationSec}s，上限 ${MAX_AUDIO_SECONDS}s）。\n\n` +
        `長錄音請去 web app 處理：${APP_URL}`,
    );
    return;
  }

  // 3. Quota check
  const dailyLimit = plan === "pro" || plan === "team" ? PRO_DAILY : FREE_DAILY;
  const monthlyLimit = plan === "pro" || plan === "team" ? PRO_MONTHLY : FREE_MONTHLY;
  const { daily, monthly } = await getUsageStats(userId);

  if (durationSec > dailyLimit - daily) {
    await sendMessage(
      chatId,
      `❌ 超過今日 quota。\n用咗 ${(daily / 60).toFixed(1)} / ` +
        `${(dailyLimit / 60).toFixed(0)} 分鐘。\n\n聽日再試。`,
    );
    return;
  }
  if (durationSec > monthlyLimit - monthly) {
    await sendMessage(
      chatId,
      `❌ 超過本月 quota。\n用咗 ${(monthly / 60).toFixed(1)} / ` +
        `${(monthlyLimit / 60).toFixed(0)} 分鐘。\n\n` +
        `升級 Pro: ${APP_URL}`,
    );
    return;
  }

  // 4. Immediate ack + typing indicator
  await sendMessage(
    chatId,
    `⏳ 收到 ${durationSec} 秒錄音，AI 處理緊...\n` +
      `通常 ${Math.max(20, Math.ceil(durationSec * 0.5))} 秒左右，請耐心等候。`,
  );
  sendChatAction(chatId, "typing"); // fire-and-forget

  // 5. Download from Telegram
  const dl = await downloadTelegramFile(mediaObj.file_id);
  if (!dl) {
    await sendMessage(chatId, "❌ 下載錄音失敗，請重新 send。");
    return;
  }

  // 6. Transcribe with Gemini
  let transcript: string;
  try {
    transcript = await transcribeWithGemini(dl.bytes, dl.mimeType);
  } catch (e) {
    console.error("Gemini error:", e);
    await sendMessage(
      chatId,
      `❌ AI 處理失敗：${String(e).substring(0, 200)}`,
    );
    return;
  }

  if (!transcript || transcript.trim().length < 5) {
    await sendMessage(
      chatId,
      `❌ AI 收唔到內容。可能錄音太靜 / 太短 / 質量差。請重新錄。`,
    );
    return;
  }

  // 7. Normalize speaker labels
  const normalized = normalizeDiarization(transcript);

  // 8. Save 落 meetings table
  const summaryWrap =
    `# 📋 純文字稿\n\n` +
    `**來源**: Telegram voice（${durationSec}s）\n\n` +
    `---\n\n` +
    `${normalized}`;

  const ext = kind === "audio" ? "mp3" : "ogg";
  const { data: saved, error: saveErr } = await supabase
    .from("meetings")
    .insert({
      user_id: userId,
      summary: summaryWrap,
      transcript: normalized,
      client: null,
      project: "Telegram",
      duration_seconds: durationSec,
      audio_filename: `telegram-${kind}-${Date.now()}.${ext}`,
    })
    .select()
    .single();

  if (saveErr) {
    console.error("save meeting failed:", saveErr);
    // Continue anyway — user still gets transcript
  }

  // 9. Reply with transcript (plain text for Telegram)
  const sendable = stripMarkdown(normalized);
  await sendMessage(chatId, "✅ 轉錄完成：\n\n" + sendable);

  // 10. Link to web app
  await sendMessage(
    chatId,
    `🔗 完整功能 (AI 摘要 / 翻譯 / 語氣分析 / 下載 Word/PDF):\n${APP_URL}`,
  );
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

  const msg = update.message || update.edited_message;
  if (!msg?.chat?.id) return new Response("ok");

  const chatId: number = msg.chat.id;
  const text: string = msg.text || msg.caption || "";

  try {
    if (text.startsWith("/start")) {
      await handleStartCommand(chatId, text);
    } else if (text === "/help") {
      await sendMessage(
        chatId,
        `ℹ️ Minute.hk Bot — 命令：\n\n` +
          `/start <code> — 連接 Minute.hk account\n` +
          `/help — 呢個訊息\n\n` +
          `直接 send voice / audio file → 自動 transcribe + 識別講者`,
      );
    } else if (msg.voice) {
      await handleVoice(chatId, msg.voice, "voice");
    } else if (msg.audio) {
      await handleVoice(chatId, msg.audio, "audio");
    } else {
      await sendMessage(
        chatId,
        `👋 Hi! Send /help 睇命令清單，或者直接 send voice message。`,
      );
    }
  } catch (e) {
    console.error("Handler error:", e);
  }

  return new Response("ok");
});
