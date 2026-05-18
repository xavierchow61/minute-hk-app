-- Minute.hk - Migration v2: Add user customization columns
-- 喺 Supabase Dashboard → SQL Editor 跑呢段

ALTER TABLE user_plans ADD COLUMN IF NOT EXISTS company_name TEXT;
ALTER TABLE user_plans ADD COLUMN IF NOT EXISTS industry TEXT DEFAULT 'generic';
ALTER TABLE user_plans ADD COLUMN IF NOT EXISTS jargon TEXT DEFAULT '';
ALTER TABLE user_plans ADD COLUMN IF NOT EXISTS summary_length TEXT DEFAULT 'medium';

-- 允許用戶 update 自己嘅 settings（補充 SELECT policy 已有）
CREATE POLICY "Users update own plan settings" ON user_plans
    FOR UPDATE USING (auth.uid() = user_id);

-- Done
