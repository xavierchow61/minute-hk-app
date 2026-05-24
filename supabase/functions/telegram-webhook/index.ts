// Telegram Bot webhook handler — Session 1: auth + echo only
//
// Receives incoming Telegram updates (messages from users). Currently handles:
//   /start <code>  → link Telegram chat to Minute.hk account
//   voice / audio  → echo back placeholder (no Gemini processing yet)
//   other          → friendly hint
//
// Deploy:
//   supabase functions deploy telegram-webhook --project-ref <your-ref>
//
// Required secrets (set via Supabase Dashboard → Edge Functions → Secrets):
//   TELEGRAM_BOT_TOKEN — from @BotFather
//   (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY auto-provided by Supabase)
//
// Configure Telegram webhook (one-time):
//   curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<FUNCTION_URL>"
//   FUNCTION_URL = https://<project-ref>.supabase.co/functions/v1/telegram-webhook

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.4";

const TELEGRAM_BOT_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN")!;
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

const TG_API = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}`;

async function sendMessage(chatId: number | string, text: string): Promise<void> {
  try {
    await fetch(`${TG_API}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        disable_web_page_preview: true,
      }),
    });
  } catch (e) {
    console.error("sendMessage failed:", e);
  }
}

async function handleStartCommand(chatId: number, text: string): Promise<void> {
  const parts = text.trim().split(/\s+/);
  if (parts.length < 2) {
    await sendMessage(
      chatId,
      "👋 Hello! 我係 Minute.hk Bot。\n\n" +
        "請先入 https://minute-hk-app.streamlit.app → ⚙️ 設定 → " +
        "🔗 連接 Telegram，跟住 click 個 link 返呢度。",
    );
    return;
  }

  const code = parts[1].trim().toUpperCase();

  const { data: linkRow, error: linkErr } = await supabase
    .from("telegram_link_codes")
    .select("user_id, expires_at, used_at")
    .eq("code", code)
    .maybeSingle();

  if (linkErr || !linkRow) {
    await sendMessage(
      chatId,
      "❌ 連接碼 `" + code + "` 無效。請喺 Minute.hk → ⚙️ 設定 重新生成。",
    );
    return;
  }

  if (linkRow.used_at) {
    await sendMessage(chatId, "❌ 呢個連接碼已被使用過。請重新生成一條。");
    return;
  }

  if (new Date(linkRow.expires_at) < new Date()) {
    await sendMessage(chatId, "❌ 連接碼已過期（10 分鐘有效）。請重新生成。");
    return;
  }

  // 更新 user_plans.telegram_chat_id + mark code as used
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
    "🎉 連接成功！\n\n" +
      "返 Minute.hk → ⚙️ 設定 refresh，應該見到 Connected ✓。\n\n" +
      "之後處理完錄音可以撳「📤 Send 落 Telegram」推 summary 過嚟。\n\n" +
      "⏳ Send voice message 直接 transcribe 嘅功能仲喺開發中，下個 update 加。",
  );
}

async function handleVoiceOrAudio(
  chatId: number,
  durationSec: number,
): Promise<void> {
  await sendMessage(
    chatId,
    `📨 收到你嘅錄音（${durationSec} 秒）。\n\n` +
      "⏳ 自動 transcribe 同 AI 分析嘅功能仲喺開發中，" +
      "下個 update 會啟用。請耐心等候 ✨",
  );
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("ok", { status: 200 });
  }

  let update: any;
  try {
    update = await req.json();
  } catch (_e) {
    return new Response("invalid json", { status: 400 });
  }

  console.log("Telegram update:", JSON.stringify(update));

  const msg = update.message || update.edited_message;
  if (!msg) return new Response("ok");

  const chatId = msg.chat?.id;
  const text: string = msg.text || msg.caption || "";

  if (!chatId) return new Response("ok");

  try {
    if (text.startsWith("/start")) {
      await handleStartCommand(chatId, text);
    } else if (msg.voice || msg.audio) {
      const duration = msg.voice?.duration ?? msg.audio?.duration ?? 0;
      await handleVoiceOrAudio(chatId, duration);
    } else if (text === "/help") {
      await sendMessage(
        chatId,
        "ℹ️ Minute.hk Bot — 命令：\n\n" +
          "/start <code> — 連接你 Minute.hk account\n" +
          "/help — 呢個訊息\n\n" +
          "之後可以直接 send voice / audio file 自動處理（開發中）。",
      );
    } else {
      await sendMessage(
        chatId,
        "👋 Hi! Send /help 睇命令清單。",
      );
    }
  } catch (e) {
    console.error("Handler error:", e);
  }

  return new Response("ok");
});
