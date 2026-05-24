-- Migration v6: Telegram bot linking via /start <code>
--
-- For Option B (full bot integration). User generates a one-time link code
-- in Settings, opens https://t.me/YourBot?start=<code>, taps START. Bot's
-- webhook (Supabase Edge Function) looks up the code, marks it used, stores
-- the user's chat_id on user_plans.telegram_chat_id (from v5).
--
-- Codes are single-use, 10-minute TTL.

CREATE TABLE IF NOT EXISTS telegram_link_codes (
  code TEXT PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_telegram_link_codes_user
  ON telegram_link_codes (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_telegram_link_codes_unused
  ON telegram_link_codes (code)
  WHERE used_at IS NULL;

ALTER TABLE telegram_link_codes ENABLE ROW LEVEL SECURITY;

-- Users can read / insert their own codes
-- DROP+CREATE pattern 令 migration 可以重複 run 唔出錯 (PostgreSQL 無
-- "CREATE POLICY IF NOT EXISTS" 嘅 syntax)
DROP POLICY IF EXISTS "Users see own link codes" ON telegram_link_codes;
CREATE POLICY "Users see own link codes" ON telegram_link_codes
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users insert own link codes" ON telegram_link_codes;
CREATE POLICY "Users insert own link codes" ON telegram_link_codes
  FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Note: The Edge Function uses the service_role key which bypasses RLS,
-- so it can update used_at and look up codes for any user.
