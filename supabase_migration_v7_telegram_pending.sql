-- Migration v7: telegram_pending_voice table
--
-- Telegram bot 收到 voice → 用 inline keyboard 問用戶要 summary 定 transcribe.
-- 因為 Telegram callback_data 限 64 byte (file_id 已經佔 60+), 所以用 bigserial
-- ID 做中介, 將 file_id / duration / user_id 暫存喺 DB.
--
-- User tap button → callback_query 帶 "summary:<id>" / "transcribe:<id>"
-- Edge Function 用 id 揾返 pending row → 處理 → 刪 row.
--
-- 10-min TTL, expired rows safe to delete (orphans don't matter, no PII).

CREATE TABLE IF NOT EXISTS telegram_pending_voice (
  id BIGSERIAL PRIMARY KEY,
  chat_id TEXT NOT NULL,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  file_id TEXT NOT NULL,
  duration_sec INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('voice', 'audio')),
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telegram_pending_chat
  ON telegram_pending_voice (chat_id, created_at DESC);

ALTER TABLE telegram_pending_voice ENABLE ROW LEVEL SECURITY;
-- Edge Function 用 service_role key，bypass RLS。
-- 唔需要 user-facing policies (用戶 web app 唔會 query 呢個 table).
