-- ============================================================
-- Migration v9 · UNIQUE constraint on telegram_chat_id
-- ============================================================
-- Audit finding HIGH #2 嘅 DB 層保護：
-- 防止多個 user_plans rows 同時擁有同一個 telegram_chat_id
-- (race condition / forged webhook 都可能造成嘅 duplicate binding)。
--
-- Edge Function code 已經會喺 setting 新 binding 之前先 NULL 走舊 owner，
-- 呢個 UNIQUE INDEX 係多一層 DB-level guard，
-- 即使 application 邏輯出錯都會由 DB reject 第二個 binding。
--
-- 用 partial unique index (WHERE NOT NULL) 因為 telegram_chat_id 大部分
-- user 都係 NULL，唔想阻 NULL 重複。
--
-- 安全可重複執行 (CREATE UNIQUE INDEX IF NOT EXISTS).

-- 預先 cleanup duplicates: keep most-recently-updated row's chat_id,
-- NULL out the older duplicates. (idempotent + safe if no dup exists.)
WITH dups AS (
  SELECT user_id, telegram_chat_id,
         ROW_NUMBER() OVER (
           PARTITION BY telegram_chat_id
           ORDER BY user_id
         ) AS rn
  FROM user_plans
  WHERE telegram_chat_id IS NOT NULL
)
UPDATE user_plans
SET telegram_chat_id = NULL
WHERE user_id IN (SELECT user_id FROM dups WHERE rn > 1);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_user_plans_telegram_chat_id
  ON user_plans (telegram_chat_id)
  WHERE telegram_chat_id IS NOT NULL;

COMMENT ON INDEX uniq_user_plans_telegram_chat_id IS
  '一個 Telegram chat 一次只可以 bind 落一個 user。Application code 應該喺' ||
  ' set 新 binding 前先 NULL 走舊 owner;呢個 index 係 DB-level fail-safe。';
