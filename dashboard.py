"""Dashboard analytics + Word cloud generation"""
import io
import re
from collections import Counter


# Stop words 黑名單（中英）
STOPWORDS = {
    # 中文虛詞
    "的", "了", "是", "我", "你", "佢", "我哋", "你哋", "佢哋",
    "一個", "呢個", "嗰個", "就係", "就喺", "係咁", "因為",
    "可以", "唔", "唔係", "都", "都會", "都要", "佢嘅", "我嘅",
    "其實", "其他", "或者", "或", "同埋", "之後", "之前", "已經",
    "繼續", "需要", "可能", "如果", "點樣", "點解", "邊個",
    "今日", "今次", "今個", "好嘅", "好多", "好少",
    "but", "and", "or", "is", "are", "the", "a", "an",
    "for", "to", "of", "in", "on", "at", "by", "with",
    "this", "that", "i", "you", "we", "they", "it",
    "be", "will", "would", "can", "could", "should",
    "yes", "no", "ok", "hi", "hello", "thanks", "thank",
    "have", "has", "had", "do", "does", "did", "so", "but",
    # 紀要常用 section names
    "會議", "紀要", "基本", "資訊", "重點", "議題", "決議",
    "事項", "action", "items", "風險", "跟進", "客戶", "項目",
    "錄音", "時長", "生成", "時間", "類型", "ai", "minutes",
}


def extract_keywords(text: str, top_n: int = 50) -> list[tuple[str, int]]:
    """
    用 jieba 切割中英文，返回 top N 關鍵字 + count
    """
    try:
        import jieba
    except ImportError:
        # Fallback: 簡單 regex
        return _extract_keywords_simple(text, top_n)

    # 去 markdown / 標點
    cleaned = re.sub(r"[#*`_~|>\[\](){}<>\-=+\\/\n\t]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned)

    words = jieba.lcut(cleaned, cut_all=False)
    counter = Counter()
    for w in words:
        w = w.strip().lower()
        if len(w) < 2:
            continue
        if w in STOPWORDS:
            continue
        if w.isdigit():
            continue
        if not any(c.isalnum() or '一' <= c <= '鿿' for c in w):
            continue
        counter[w] += 1

    return counter.most_common(top_n)


def _extract_keywords_simple(text: str, top_n: int = 50) -> list[tuple[str, int]]:
    """Fallback: simple word extraction without jieba"""
    cleaned = re.sub(r"[#*`_~|>\[\](){}<>\-=+\\/\n\t]", " ", text)
    # 抽英文詞 OR 連續中文 2-4 字
    tokens = re.findall(r"[a-zA-Z]{3,}|[一-鿿]{2,4}", cleaned)
    counter = Counter()
    for t in tokens:
        t = t.lower()
        if t in STOPWORDS or t.isdigit():
            continue
        counter[t] += 1
    return counter.most_common(top_n)


def generate_wordcloud_image(text: str, max_words: int = 100) -> bytes | None:
    """
    生成 word cloud image (PNG bytes)
    返回 None 如果 wordcloud library 唔 work
    """
    try:
        from wordcloud import WordCloud
    except ImportError:
        return None

    keywords = extract_keywords(text, top_n=max_words)
    if not keywords:
        return None

    word_freq = dict(keywords)

    # Try Chinese font paths (Streamlit Cloud uses Noto CJK from packages.txt)
    font_candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
    ]
    font_path = None
    from pathlib import Path
    for f in font_candidates:
        if Path(f).exists():
            font_path = f
            break

    wc = WordCloud(
        width=800,
        height=400,
        background_color="white",
        max_words=max_words,
        font_path=font_path,
        colormap="Blues",
        relative_scaling=0.5,
        min_font_size=10,
    )
    wc.generate_from_frequencies(word_freq)
    img = wc.to_image()

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
