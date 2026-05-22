# UAT 環境 — 設置同工作流程

兩個 Streamlit Cloud app instance，兩個 branch，兩套 secrets。
喺 UAT 試到滿意先 merge 落 main（prod）。

## 架構

```
GitHub: xavierchow61/minute-hk-app
│
├── main branch  ──► minute-hk-app.streamlit.app       (Prod)
│                    Supabase: 正式 project
│                    Stripe  : live mode
│                    ENV     : (空 / "production")
│
└── uat branch   ──► minute-hk-app-uat.streamlit.app   (UAT)
                     Supabase: UAT-only project
                     Stripe  : test mode
                     ENV     : "uat"  ← 觸發頂部黃色 banner
```

任何時候只要 push 到對應 branch，個 Streamlit Cloud app 都會自動 redeploy。

---

## 一次性設置（要做 4 樣嘢）

### 1. 開 UAT Supabase project

1. 入 https://supabase.com/dashboard
2. New project → 名 e.g. `minute-hk-uat`，揀同 prod 一樣嘅 region（HK 用戶用 Singapore）
3. 攞 `Project URL` + `anon key`（喺 Settings → API）
4. 跑 schema migrations，順序：
   ```
   supabase_schema.sql
   supabase_migration_v2.sql
   supabase_migration_v3_invite.sql
   supabase_migration_v4_softdelete.sql
   ```
   每個 file copy paste 入 Supabase Dashboard → SQL Editor → Run

> ⚠️ 一定要用獨立 project。UAT 試錯，prod user 嘅 meetings 唔應該被污染。

### 2. 攞 Stripe test keys

1. 入 https://dashboard.stripe.com
2. 右上角 toggle 切到 **Test mode**
3. Developers → API keys → 攞 `Secret key`（`sk_test_...`）
4. Products → 建一個 test 嘅 Pro plan → 攞 `Price ID`（`price_...`）

> Test mode 永遠免費。試 checkout 用 [Stripe test cards](https://docs.stripe.com/testing#cards)，例如 `4242 4242 4242 4242`。

### 3. 開 Streamlit Cloud UAT app

1. 入 https://share.streamlit.io
2. **New app** → 揀 repo `xavierchow61/minute-hk-app`
3. **Branch**: 揀 `uat`（唔係 main）
4. **App URL** 隨意，建議 `minute-hk-app-uat`
5. 揭 `Advanced settings` → **Secrets**，貼入：
   ```toml
   ENV = "uat"

   GEMINI_API_KEY = "AIzaSy..."           # 可以同 prod share
   SUPABASE_URL = "https://[UAT project].supabase.co"
   SUPABASE_ANON_KEY = "eyJhbGc..."        # UAT project 嘅 anon key
   STRIPE_SECRET_KEY = "sk_test_..."
   STRIPE_PRICE_ID_PRO = "price_..."       # test mode 嘅 price
   APP_URL = "https://minute-hk-app-uat.streamlit.app"
   ```
6. Deploy

成功 deploy 後，個 UAT app 頂部會見到黃色 banner「🧪 UAT 測試版」。

### 4.（可選）GitHub 設 branch protection

入 GitHub repo → Settings → Branches → Add rule for `main`：
- ☑ Require pull request before merging
- ☑ Require status checks to pass

咁可以避免不小心直接 push 到 main。

---

## 日常 workflow

### 改 code、試、上線

```bash
# 1. 切到 uat branch
git checkout uat
git pull

# 2. 改 code、commit
# ...edit files...
git add .
git commit -m "Feat: 新功能 X"
git push

# 3. UAT site 自動 redeploy（~1-2 分鐘）
# 開 https://minute-hk-app-uat.streamlit.app 試到滿意

# 4. Merge 落 main 上 prod（建議用 PR）
gh pr create --base main --head uat --title "Promote: 新功能 X 到 prod"
# 入 GitHub UI 撳 Merge

# 或者直接 merge（如果只係 solo dev）:
git checkout main
git merge uat
git push
```

### 同步 main 嘅 hotfix 返 uat

如果直接喺 main 改咗 hotfix（緊急修）：

```bash
git checkout uat
git merge main
git push
```

咁 uat 同 main 保持同步。

---

## 常見坑

| 問題 | 原因 | 解法 |
|------|------|------|
| UAT 冇黃色 banner | `ENV` secret 未設成 `"uat"` | Streamlit Cloud → Settings → Secrets 改 |
| UAT user 見到 prod 數據 | UAT 用緊 prod Supabase | secrets 嘅 `SUPABASE_URL` 改返 UAT project |
| UAT 試 checkout 真係扣錢 | Stripe 用咗 live key | 換 `sk_test_...` |
| 改完 secrets 冇生效 | Streamlit 要 reboot app | App 右上 ☰ → Reboot app |
| `main` 同 `uat` 分叉太遠 conflict | 太耐冇 merge | 經常 `git merge main` 落 uat |
