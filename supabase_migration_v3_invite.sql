-- =========================================================
-- Minute.hk - Migration v3: Invite codes (beta tester gating)
-- 用法：
--   1. Supabase Dashboard → SQL Editor → paste 全部 → Run
--   2. 然後 insert 幾個 code (見最下面)
--   3. 比 tester 用個 code 註冊，自動升 Pro
-- =========================================================

CREATE TABLE IF NOT EXISTS invite_codes (
    code            text PRIMARY KEY,
    note            text,                  -- 比邊個用 / 用途
    created_at      timestamptz DEFAULT now(),
    used_by_user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    used_at         timestamptz,
    auto_upgrade_to text DEFAULT 'pro'     -- 自動升嘅 plan
);

-- RLS：只有 service role 可以 read/write（client 透過 Edge Function 或 server-side 用）
-- 但我哋而家係 client-side Streamlit，要 anon role 可以 SELECT 同 UPDATE 自己 claim 嘅 code
ALTER TABLE invite_codes ENABLE ROW LEVEL SECURITY;

-- 所有人可以 read（要 check code 係咪 valid 同未用）
DROP POLICY IF EXISTS "Anyone can read invite codes" ON invite_codes;
CREATE POLICY "Anyone can read invite codes" ON invite_codes
    FOR SELECT
    USING (true);

-- 只可以 update 未用嘅 code（將 used_by_user_id 設成自己）
DROP POLICY IF EXISTS "Anyone can claim unused code" ON invite_codes;
CREATE POLICY "Anyone can claim unused code" ON invite_codes
    FOR UPDATE
    USING (used_by_user_id IS NULL)
    WITH CHECK (used_by_user_id = auth.uid());

-- =========================================================
-- 插入測試用 codes（改成你想要嘅 code 字串）
-- =========================================================
-- 範例：6 個 beta tester codes
INSERT INTO invite_codes (code, note) VALUES
    ('BETA-2026-A1', '朋友 A - beta tester'),
    ('BETA-2026-A2', '朋友 B - beta tester'),
    ('BETA-2026-A3', '朋友 C - beta tester'),
    ('BETA-2026-A4', '同事 D - beta tester'),
    ('BETA-2026-A5', '同事 E - beta tester'),
    ('BETA-2026-VIP', 'VIP 用 - 你自己 / demo')
ON CONFLICT (code) DO NOTHING;

-- 之後想多插幾個：
-- INSERT INTO invite_codes (code, note) VALUES ('BETA-2026-XYZ', '某某') ON CONFLICT DO NOTHING;

-- 查邊個 code 用咗未：
-- SELECT code, note, used_by_user_id, used_at FROM invite_codes ORDER BY created_at DESC;
