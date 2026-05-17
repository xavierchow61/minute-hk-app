-- Minute.hk Supabase Schema
-- 喺 Supabase Dashboard → SQL Editor 跑呢段 SQL
-- 自動建 table + RLS（Row Level Security 確保 user 只睇到自己 data）

-- ============================================================
-- Table: meetings (主表)
-- ============================================================
CREATE TABLE IF NOT EXISTS meetings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    client TEXT,
    project TEXT,
    duration_seconds REAL DEFAULT 0,
    audio_filename TEXT,
    summary TEXT NOT NULL,
    transcript TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_meetings_user_id ON meetings(user_id);
CREATE INDEX IF NOT EXISTS idx_meetings_created_at ON meetings(created_at DESC);

-- RLS（Row Level Security）
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own meetings" ON meetings
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users insert own meetings" ON meetings
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users update own meetings" ON meetings
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users delete own meetings" ON meetings
    FOR DELETE USING (auth.uid() = user_id);


-- ============================================================
-- Table: user_plans (subscription tier)
-- ============================================================
CREATE TABLE IF NOT EXISTS user_plans (
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'pro', 'team')),
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    subscription_ends_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE user_plans ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own plan" ON user_plans
    FOR SELECT USING (auth.uid() = user_id);


-- ============================================================
-- Trigger: 註冊新 user 時自動建 user_plans 記錄
-- ============================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_plans (user_id, plan)
    VALUES (NEW.id, 'free')
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- ============================================================
-- Done! 可以開始用啦
-- ============================================================
-- 確認所有嘢起好：
-- SELECT 'Tables:', COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';
-- SELECT 'RLS enabled:', COUNT(*) FROM pg_tables WHERE schemaname = 'public' AND rowsecurity = true;
