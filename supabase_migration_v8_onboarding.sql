-- ============================================================
-- Migration v8 · Onboarding dismissed flag
-- ============================================================
-- 加一個 boolean column 落 user_plans，記住用戶有冇 dismiss 第一次
-- 入 app 時嘅 4-card 教學。Dismiss 一次之後永久收埋，但教學仲可以
-- 喺「📖 教學」tab 重溫。
--
-- 安全可重複執行 (ADD COLUMN IF NOT EXISTS)。

ALTER TABLE user_plans
  ADD COLUMN IF NOT EXISTS onboarding_dismissed BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN user_plans.onboarding_dismissed IS
  'TRUE = 用戶已 dismiss 首次入 app 嘅教學卡。教學仍然可由 「教學」 tab 重溫。';
