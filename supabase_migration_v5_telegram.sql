-- Migration v5: Telegram integration
--
-- Add telegram_chat_id column to user_plans so we can push meeting summaries
-- to the user's Telegram chat via Bot API. Stored as TEXT (chat_id is numeric
-- but can be very large in Telegram's API).
--
-- Outgoing-only bot — no webhook needed. User pastes their chat_id once via
-- @userinfobot, we store it, then "📤 Send to Telegram" button on result
-- section calls api.telegram.org/bot<token>/sendMessage to push.

ALTER TABLE user_plans
  ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT NULL;
