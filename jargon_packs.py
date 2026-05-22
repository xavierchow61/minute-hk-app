"""預載行業 jargon pack — 一鍵套用常用詞典

每個 pack 收錄 50-100 個 HK 行業常用詞，主要 target：
  - HK 專用 acronyms (HKFRS, HKMA, HKIAC...)
  - HK 法例 / 機構 (Cap. 622, ICAC, HA...)
  - 行業內常見人名 / 公司 (KPMG, HSBC...)
  - Whisper 易錯嘅技術詞 (HbA1c, HKAS 1...)
"""

PACKS: dict[str, dict] = {
    "accounting": {
        "label": "📊 會計 / 審計",
        "description": "HKFRS、IRD、四大、稅務、審計常用詞",
        "terms": [
            # 會計準則
            "HKFRS", "HKAS", "HKICPA", "HKSA", "IFRS", "IAS", "GAAP",
            "HKFRS 9", "HKFRS 15", "HKFRS 16", "HKFRS 17", "HKAS 1", "HKAS 36", "HKAS 38",
            # 稅務
            "IRD", "稅務局", "BIR", "profits tax", "salaries tax", "property tax",
            "利得稅", "薪俸稅", "物業稅", "印花稅", "stamp duty", "AVD", "BSD", "SSD",
            # 四大 + firms
            "KPMG", "PwC", "Deloitte", "EY", "BDO", "Mazars", "RSM", "Grant Thornton",
            "big 4", "四大", "Crowe", "Baker Tilly",
            # 職稱 + 證書
            "CPA", "ACCA", "HKCPA", "CGA", "CFA", "CIA", "CISA",
            "core auditor", "audit senior", "audit manager", "audit partner",
            "核數", "核數師", "註冊會計師", "註冊核數師", "PA", "RA",
            # 報表 / 分錄
            "balance sheet", "income statement", "P&L", "cash flow",
            "trial balance", "GL", "general ledger", "journal entry",
            "accruals", "prepayments", "deferred income", "deferred tax",
            "depreciation", "amortisation", "goodwill", "impairment",
            "應收", "應付", "折舊", "攤銷", "商譽", "減值",
            "AR", "AP", "WIP", "FX", "FX gain", "FX loss",
            # 工作流程
            "working paper", "audit confirmation", "circularization",
            "rollforward", "tickmark", "lead schedule", "PBC",
            "Companies Ordinance", "Cap. 622", "Cap. 32", "Companies Registry",
        ],
    },

    "legal": {
        "label": "⚖️ 法律",
        "description": "HKIAC、法院、Cap. 622、conveyancing、合約常用詞",
        "terms": [
            # 機構 + 法庭
            "HKIAC", "CIArb", "SIAC", "ICC",
            "Court of Final Appeal", "CFA", "High Court", "District Court",
            "Magistrate", "Court of Appeal",
            "終審法院", "高等法院", "區域法院", "裁判法院", "上訴法庭",
            "DOJ", "律政司", "ICAC", "廉政公署", "廉署", "ORO", "OFTA",
            "SFC", "HKMA", "MPFA", "Estate Duty Office",
            # 法例
            "Basic Law", "BL", "基本法",
            "Cap. 622", "Cap. 32", "Cap. 200", "Cap. 281", "Cap. 88",
            "Companies Ordinance", "Companies WUMP", "Crimes Ordinance",
            "Securities and Futures Ordinance", "SFO",
            "POBO", "Prevention of Bribery Ordinance",
            "PDPO", "Personal Data Privacy Ordinance",
            "防止賄賂條例", "個人資料隱私條例",
            # 文件 + 概念
            "DMC", "Deed of Mutual Covenant", "公契",
            "conveyancing", "due diligence", "DD", "indemnity", "warranty",
            "representations and warranties", "covenants", "undertaking",
            "consideration", "earnest", "deposit",
            "judgment", "ruling", "order", "injunction",
            "counsel", "opinion", "brief", "instruction sheet", "court bundle",
            "writ", "summons", "affidavit", "affirmation", "statutory declaration",
            # 職稱
            "barrister", "solicitor", "trainee solicitor", "paralegal",
            "Senior Counsel", "SC", "King's Counsel", "KC",
            "事務律師", "大律師", "資深大律師",
            # 合規
            "AML", "CFT", "KYC", "CDD", "EDD", "PEP", "STR",
            "反洗錢", "認識你的客戶",
        ],
    },

    "medical": {
        "label": "🏥 醫療",
        "description": "HA、醫院縮寫、ICD-10、化驗指標、常見疾病",
        "terms": [
            # 機構 + 醫院
            "HA", "Hospital Authority", "醫管局", "DH", "Department of Health", "衞生署",
            "QMH", "Queen Mary Hospital", "瑪麗醫院",
            "PMH", "Princess Margaret Hospital", "瑪嘉烈醫院",
            "QEH", "Queen Elizabeth Hospital", "伊利沙伯醫院",
            "PWH", "Prince of Wales Hospital", "威爾斯親王醫院",
            "KWH", "Kwong Wah Hospital", "廣華醫院",
            "UCH", "United Christian Hospital", "基督教聯合醫院",
            "TMH", "Tuen Mun Hospital", "屯門醫院",
            "PYNEH", "Pamela Youde", "東區醫院",
            "RH", "Ruttonjee Hospital", "律敦治醫院",
            "NDH", "North District Hospital", "北區醫院",
            "TKOH", "Tseung Kwan O Hospital",
            "CUHK", "HKU", "CU Med", "HKUMed", "中大醫學院", "港大醫學院",
            # 職稱
            "GP", "consultant", "specialist", "MO", "AP", "HO", "PMO",
            "RN", "EN", "APN", "WM", "NS",
            "physician", "surgeon", "anaesthetist", "anaesthesiologist",
            "西醫", "中醫", "註冊醫生", "註冊護士", "藥劑師",
            # 檢查 / Imaging
            "ECG", "EKG", "EEG", "EMG", "MRI", "CT", "CTA", "MRA",
            "X-ray", "PET", "PET-CT", "ultrasound", "USG", "DEXA",
            "心電圖", "腦電圖", "磁力共振", "電腦掃描", "超聲波",
            # 化驗指標 (Whisper 經常錯)
            "HbA1c", "FBS", "RBS", "OGTT", "BUN", "Cr", "eGFR",
            "CRP", "ESR", "INR", "PT", "PTT", "APTT", "BNP", "NT-proBNP",
            "troponin", "CK", "CK-MB", "LDH", "ALP", "ALT", "AST", "GGT",
            "LDL", "HDL", "TG", "TC", "PSA", "CEA", "AFP", "CA-125",
            "Hb", "Hct", "WBC", "RBC", "platelet", "MCV", "MCH", "MCHC",
            "TSH", "T3", "T4", "fT3", "fT4",
            # 疾病
            "DM", "diabetes mellitus", "type 1 DM", "type 2 DM",
            "HTN", "hypertension", "CAD", "IHD", "AMI", "STEMI", "NSTEMI",
            "CHF", "AF", "afib", "atrial fibrillation",
            "COPD", "asthma", "CKD", "ESRD",
            "CVA", "stroke", "TIA", "AKI",
            "糖尿病", "高血壓", "冠心病", "心房顫動", "慢性腎病", "中風",
            # ICD / 系統
            "ICD-10", "ICD-11", "SNOMED", "LOINC", "DRG",
            "HA Go", "ePR", "CMS", "eHealth",
            # 藥物常用
            "Panadol", "paracetamol", "ibuprofen", "metformin",
            "amlodipine", "lisinopril", "atorvastatin", "warfarin",
            "aspirin", "clopidogrel",
        ],
    },

    "sales": {
        "label": "💼 銷售",
        "description": "Pipeline、CAC、SFDC、銷售流程",
        "terms": [
            # 職稱
            "BD", "AE", "Account Executive", "SDR", "BDR",
            "AM", "Account Manager", "CSM", "Customer Success",
            "KAM", "Key Account Manager", "Sales Engineer", "SE",
            "RevOps", "Sales Ops",
            # 指標
            "MRR", "ARR", "CAC", "LTV", "NRR", "GRR", "CLV",
            "NPS", "CSAT", "CES", "churn", "expansion", "renewal",
            "win rate", "ASP", "ACV", "TCV", "quota", "attainment",
            "OTE", "commission", "accelerator", "decelerator", "kicker",
            # 漏斗
            "pipeline", "MQL", "SQL", "lead", "opportunity", "prospect",
            "qualified", "discovery", "demo", "POC", "POV",
            "RFP", "RFI", "RFQ", "BANT", "MEDDIC", "MEDDPICC", "SPICED",
            "upsell", "cross-sell", "land and expand",
            # 工具
            "Salesforce", "SFDC", "HubSpot", "Pipedrive", "Outreach",
            "Salesloft", "Apollo", "ZoomInfo", "Gong", "Chorus",
            "LinkedIn Sales Navigator", "SalesNav",
            # 行動
            "cold call", "cold email", "warm intro", "referral",
            "discovery call", "demo call", "follow-up call",
            "objection handling", "negotiation", "close",
            "champion", "decision maker", "DM", "economic buyer",
            "blocker", "detractor", "signal", "intent",
            # 廣東話 / 中文 sales 詞
            "跟客", "跟進", "落單", "傾單", "傾客", "客戶", "大客",
        ],
    },

    "education": {
        "label": "🎓 教育",
        "description": "DSE、學制、學校類型、SBA",
        "terms": [
            "HKDSE", "DSE", "JUPAS", "non-JUPAS", "EAS",
            "CE", "AL", "HKCEE", "HKALE",
            "HKEAA", "考評局", "EDB", "教育局",
            "BAFS", "ICT", "VA", "ME", "PE",
            "IES", "SBA", "School Based Assessment",
            "IB", "IBDP", "IGCSE", "GCE", "A-Level", "AP", "SAT",
            "POA", "Allocation", "central allocation", "self-applied",
            "BAND 1", "BAND 2", "BAND 3", "Band 1A",
            "DSS", "direct subsidy scheme", "aided", "official", "private",
            "international school", "ESF", "HKIS", "CIS", "GSIS",
            "校長", "副校長", "主任", "班主任", "輔導主任",
            "Form 1", "Form 6", "F.1", "F.6", "S1", "S6",
            "primary", "secondary", "kindergarten", "K1", "K2", "K3",
            "津貼", "直資", "官校", "私校", "國際學校",
            "考試", "測驗", "默書", "課程",
            "tutor", "tutorial", "remedial", "extension",
        ],
    },

    "real_estate": {
        "label": "🏘️ 地產",
        "description": "DMC、樓盤、按揭、土地註冊",
        "terms": [
            "DMC", "Deed of Mutual Covenant", "公契",
            "OP", "occupation permit", "入伙紙",
            "CC", "completion certificate",
            "saleable area", "SA", "gross floor area", "GFA",
            "實用面積", "建築面積", "效率比",
            # Housing
            "HOS", "居屋", "PRH", "公屋", "綠表", "白表", "白居二",
            "HKHA", "Housing Authority", "房委會", "HD", "Housing Department", "房屋署",
            "HKHS", "Housing Society", "房協",
            "TPS", "Tenants Purchase Scheme", "租置",
            # Agents
            "Centaline", "中原", "Midland", "美聯", "Ricacorp", "利嘉閣",
            "Hong Kong Property", "香港置業", "Q房", "World-wide",
            # 文件
            "agreement", "PASP", "FASP",
            "earnest", "細訂", "大訂", "成交日", "completion date",
            "land search", "Land Registry", "田土廳", "土地註冊處",
            "Memorial", "MRS",
            # 按揭
            "mortgage", "HIBOR", "H plan", "P plan", "P-2.5", "P-2",
            "鎖息上限", "cap rate", "LTV", "DSR",
            "stress test", "MIP", "mortgage insurance",
            "HKMC", "按揭證券公司",
            # 物業類型
            "estate", "village house", "town house", "low rise", "high rise",
            "tenement", "屋苑", "村屋", "唐樓", "洋樓", "獨立屋", "半山",
            "harbor view", "sea view", "city view", "mountain view",
            "南向", "東南向", "西曬",
        ],
    },

    "finance": {
        "label": "💰 金融",
        "description": "HKMA、HKEX、HSI、衍生工具、合規",
        "terms": [
            # 監管
            "HKMA", "SFC", "HKEX", "MPFA", "OCI", "IA", "FSDC",
            "金管局", "證監會", "港交所", "強積金局",
            "PBOC", "CSRC", "SEC", "FRC", "AMCM",
            # Market / Index
            "HSI", "Hang Seng", "HSCEI", "HSTECH", "HSIE",
            "H-shares", "A-shares", "ADR", "ETF", "REIT",
            "Stock Connect", "Bond Connect", "Wealth Connect",
            "HKEx Connect", "Shanghai-HK Connect", "Shenzhen-HK Connect",
            "HIBOR", "SOFR", "LIBOR", "EFFR",
            "USD-HKD peg", "convertibility undertaking", "linked exchange rate",
            "聯繫匯率",
            # 銀行
            "HSBC", "滙豐", "Hang Seng Bank", "恒生", "BOC", "中銀香港",
            "Standard Chartered", "SC", "渣打",
            "Citi", "JPM", "GS", "MS", "BAML", "BAC", "BoA",
            "DBS", "OCBC", "UOB",
            "ICBC", "CCB", "ABC", "BOC", "China Construction",
            # 產品
            "structured product", "structured note", "ELN", "DCN",
            "derivatives", "swap", "option", "future", "forward",
            "call", "put", "straddle", "strangle", "collar",
            "衍生工具", "期貨", "期權", "互換",
            "FCN", "knock-out", "knock-in", "barrier option",
            "bond", "fixed income", "yield", "duration", "convexity",
            "spread", "BPS", "basis points",
            # 投行
            "IPO", "secondary listing", "dual listing", "spin-off",
            "M&A", "merger", "acquisition", "LBO", "MBO",
            "listing rules", "prospectus", "red herring", "roadshow",
            "bookrunner", "underwriter", "DCM", "ECM",
            # 合規
            "KYC", "AML", "CDD", "EDD", "PEP", "STR", "CFT",
            "FATCA", "CRS", "OECD", "BEPS",
            "compliance", "custody", "settlement", "T+2", "T+1", "DVP",
            "Reg A", "Reg D", "Reg S", "144A", "QIB",
        ],
    },

    "consulting": {
        "label": "💡 顧問",
        "description": "MBB、engagement、deliverable、framework",
        "terms": [
            # Firms
            "McKinsey", "BCG", "Bain", "MBB", "Big 3",
            "Deloitte Consulting", "PwC Strategy&", "EY-Parthenon",
            "KPMG Strategy", "Accenture", "Oliver Wyman", "Roland Berger",
            "L.E.K.", "AT Kearney", "Kearney", "Booz Allen", "Mercer",
            # Workflow
            "engagement", "scoping", "kickoff", "steering committee",
            "milestone", "deliverable", "workstream", "workshop",
            "alignment", "stakeholder", "sponsor", "client lead",
            "RFP", "TOR", "Terms of Reference", "SOW", "MSA", "NDA", "COI",
            "上線", "落地", "落實",
            # 工具 / Framework
            "5-forces", "Porter's", "SWOT", "PESTLE", "PEST",
            "value chain", "BCG matrix", "Ansoff", "BCG growth-share",
            "OKR", "KPI", "balanced scorecard",
            "MECE", "Pyramid Principle", "Issue tree", "Storyline",
            "synthesis", "hypothesis", "fact base", "test", "iterate",
            # Output
            "deck", "slide", "exec summary", "ES", "one-pager",
            "kickoff deck", "interim", "final readout",
            "draft", "v1", "v2", "comments incorporated",
            # 職稱
            "Partner", "Principal", "MD", "Director",
            "Senior Manager", "EM", "Engagement Manager",
            "Associate", "Senior Associate", "Consultant", "Senior Consultant",
            "Analyst", "Business Analyst", "BA",
            "summer associate", "intern", "fellow",
            "alumnus", "alumni",
        ],
    },

    "tech": {
        "label": "💻 科技",
        "description": "Cloud、API、CI/CD、LLM、startup",
        "terms": [
            # General
            "API", "SDK", "CLI", "GUI", "UI", "UX", "REST", "GraphQL",
            "JSON", "YAML", "XML", "OAuth", "JWT", "SAML", "SSO",
            "monorepo", "polyrepo", "microservices", "monolith",
            # Code workflow
            "repo", "PR", "MR", "commit", "branch", "merge", "rebase",
            "diff", "fork", "upstream", "origin", "main", "master",
            "deploy", "rollback", "hotfix", "feature flag", "A/B test",
            # Environments
            "prod", "staging", "dev", "QA", "UAT", "sandbox", "local",
            # Cloud
            "AWS", "GCP", "Azure", "Cloudflare", "DigitalOcean", "Vercel",
            "EC2", "S3", "RDS", "Lambda", "ECS", "EKS", "Fargate",
            "Cloud Run", "Cloud Functions", "BigQuery", "Firestore",
            "VPC", "subnet", "security group", "IAM", "ACL",
            "CDN", "edge", "POP",
            # Stack
            "React", "Vue", "Angular", "Svelte", "Next.js", "Nuxt",
            "Node", "Express", "FastAPI", "Django", "Flask", "Rails",
            "Spring", "Spring Boot", ".NET",
            "Python", "TypeScript", "JavaScript", "Go", "Rust", "Java",
            "Kotlin", "Swift", "Dart", "Flutter", "React Native",
            # Data
            "Postgres", "PostgreSQL", "MySQL", "MongoDB", "Redis",
            "ClickHouse", "Snowflake", "BigQuery", "Databricks",
            "Kafka", "RabbitMQ", "SQS", "PubSub",
            "ETL", "ELT", "dbt", "Airflow", "Dagster",
            # DevOps
            "Docker", "Kubernetes", "k8s", "Helm", "Terraform",
            "Pulumi", "Ansible", "Jenkins", "GitHub Actions", "GitLab CI",
            "CircleCI", "Argo", "Argo CD",
            # AI / ML
            "LLM", "RAG", "embedding", "vector", "transformer",
            "fine-tune", "fine-tuning", "prompt", "prompt engineering",
            "OpenAI", "GPT-4", "GPT-5", "Claude", "Gemini", "Llama",
            "Anthropic", "Hugging Face", "LangChain", "LlamaIndex",
            "pgvector", "Pinecone", "Weaviate", "Qdrant", "Chroma",
            "vector DB", "vector database", "semantic search",
        ],
    },
}


def get_pack(industry_key: str) -> dict | None:
    """攞某個行業嘅 jargon pack"""
    return PACKS.get(industry_key)


def list_packs() -> list[tuple[str, dict]]:
    """全部 pack list (排好序)"""
    return list(PACKS.items())


def merge_jargon(existing: str, pack_terms: list[str]) -> str:
    """Append pack terms 入 existing jargon string, 自動 dedupe.

    Output format: comma-separated, preserve original ordering of existing items,
    then append new pack terms.
    """
    existing_set: set[str] = set()
    output_terms: list[str] = []

    # Parse existing — support both comma + newline separated
    for raw_line in (existing or "").split("\n"):
        for raw_term in raw_line.split(","):
            t = raw_term.strip()
            if t and t.lower() not in existing_set:
                existing_set.add(t.lower())
                output_terms.append(t)

    # Append pack terms (case-insensitive dedupe)
    added = 0
    for term in pack_terms:
        t = term.strip()
        if t and t.lower() not in existing_set:
            existing_set.add(t.lower())
            output_terms.append(t)
            added += 1

    return ", ".join(output_terms)


def count_terms(jargon_str: str) -> int:
    """數一個 jargon string 入面有幾多個 unique terms"""
    seen: set[str] = set()
    for raw_line in (jargon_str or "").split("\n"):
        for raw_term in raw_line.split(","):
            t = raw_term.strip().lower()
            if t:
                seen.add(t)
    return len(seen)
