-- =========================================================
-- Minute.hk - Migration v3: Invite codes + Secure plan upgrades
--
-- 安全模型：
--   1. user_plans.plan 不可由 client 直接改 (trigger 阻擋)
--   2. 邀請碼 claim 走 RPC claim_invite_code (SECURITY DEFINER, 原子)
--   3. Stripe webhook 用 service_role (bypass trigger)
--
-- 用法：
--   Supabase Dashboard → SQL Editor → paste 全部 → Run
--
-- 跑完之後：
--   - invite_codes 表 + 6 個 sample codes
--   - 普通 user 唔可以透過 API 自己升 Pro
--   - 只可以 (a) 用 invite code RPC, 或 (b) Stripe 付款後 webhook 升
-- =========================================================

-- ---------------------------------------------------------
-- 1. invite_codes 表
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS invite_codes (
    code            text PRIMARY KEY,
    note            text,
    created_at      timestamptz DEFAULT now(),
    used_by_user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    used_at         timestamptz,
    auto_upgrade_to text DEFAULT 'pro'   -- 'pro' / 'team' 等
);

ALTER TABLE invite_codes ENABLE ROW LEVEL SECURITY;

-- SELECT: 任何人可以讀 (signup 前要 validate code)
DROP POLICY IF EXISTS "Anyone can read invite codes" ON invite_codes;
CREATE POLICY "Anyone can read invite codes" ON invite_codes
    FOR SELECT
    USING (true);

-- UPDATE / INSERT / DELETE: 一律 deny (only RPC + service_role 可以改)
-- 預設冇 policy = 全部 deny

-- ---------------------------------------------------------
-- 2. Trigger: 阻擋 client 自己改 user_plans.plan
--    (Stripe webhook 用 service_role bypass; RPC 用 postgres role bypass)
-- ---------------------------------------------------------
CREATE OR REPLACE FUNCTION block_client_plan_change()
RETURNS TRIGGER AS $$
BEGIN
    -- 只當 plan 真係變咗 + 由 client role (authenticated/anon) 嚟先 raise
    -- service_role 同 postgres (SECURITY DEFINER 內) 可以照改
    IF NEW.plan IS DISTINCT FROM OLD.plan
       AND current_user IN ('authenticated', 'anon') THEN
        RAISE EXCEPTION
            'Plan changes blocked: must go through claim_invite_code RPC or Stripe webhook (caller=%)',
            current_user;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS no_client_plan_change ON user_plans;
CREATE TRIGGER no_client_plan_change
    BEFORE UPDATE ON user_plans
    FOR EACH ROW EXECUTE FUNCTION block_client_plan_change();

-- ---------------------------------------------------------
-- 3. RPC: claim_invite_code (原子操作，SECURITY DEFINER 跳 trigger)
--    Returns jsonb: {"ok": true/false, "plan": "pro" | "error": "..."}
-- ---------------------------------------------------------
CREATE OR REPLACE FUNCTION claim_invite_code(p_code text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_uid          uuid := auth.uid();
    v_target_plan  text;
    v_used_by      uuid;
    v_norm         text := trim(p_code);
BEGIN
    IF v_uid IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', '請先登入');
    END IF;

    IF v_norm IS NULL OR v_norm = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', '請填邀請碼');
    END IF;

    -- Lock + check code 原子 (FOR UPDATE 防 race)
    SELECT auto_upgrade_to, used_by_user_id
      INTO v_target_plan, v_used_by
      FROM invite_codes
      WHERE code = v_norm
      FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', '邀請碼唔啱');
    END IF;

    IF v_used_by IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', '呢個邀請碼已經用咗');
    END IF;

    v_target_plan := COALESCE(v_target_plan, 'pro');

    -- Mark code claimed
    UPDATE invite_codes
       SET used_by_user_id = v_uid,
           used_at = now()
     WHERE code = v_norm;

    -- Upgrade user_plans (trigger 唔會 raise 因為 current_user = postgres)
    UPDATE user_plans
       SET plan = v_target_plan,
           updated_at = now()
     WHERE user_id = v_uid;

    -- 安全網：如果 handle_new_user trigger 仲未 fire (race)，插返一行
    IF NOT FOUND THEN
        INSERT INTO user_plans (user_id, plan)
        VALUES (v_uid, v_target_plan)
        ON CONFLICT (user_id) DO UPDATE
        SET plan = EXCLUDED.plan,
            updated_at = now();
    END IF;

    RETURN jsonb_build_object('ok', true, 'plan', v_target_plan);

EXCEPTION
    WHEN OTHERS THEN
        RETURN jsonb_build_object('ok', false, 'error', SQLERRM);
END;
$$;

-- 只 authenticated user 可以 call (anon 唔得 - 必須登入先)
REVOKE EXECUTE ON FUNCTION claim_invite_code(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION claim_invite_code(text) FROM anon;
GRANT EXECUTE ON FUNCTION claim_invite_code(text) TO authenticated;

-- ---------------------------------------------------------
-- 4. Sample invite codes (改成你想要嘅 code)
-- ---------------------------------------------------------
INSERT INTO invite_codes (code, note) VALUES
    ('BETA-2026-A1', '朋友 A - beta tester'),
    ('BETA-2026-A2', '朋友 B - beta tester'),
    ('BETA-2026-A3', '朋友 C - beta tester'),
    ('BETA-2026-A4', '同事 D - beta tester'),
    ('BETA-2026-A5', '同事 E - beta tester'),
    ('BETA-2026-VIP', 'VIP / demo 用')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------
-- 之後想多插 code:
--   INSERT INTO invite_codes (code, note) VALUES ('XYZ', '某人') ON CONFLICT DO NOTHING;
--
-- 查邊個用咗:
--   SELECT code, note, used_by_user_id, used_at FROM invite_codes ORDER BY created_at DESC;
--
-- 測試自己升 Pro 攻擊 (應該 raise exception):
--   UPDATE user_plans SET plan = 'pro' WHERE user_id = auth.uid();
-- ---------------------------------------------------------
