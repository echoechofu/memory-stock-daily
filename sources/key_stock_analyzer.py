"""
重点公司动态分析模块 - MU / SNDK / NVDA / Samsung / SK hynix
从 Google News 按 ticker 抓取的新闻中提取 IR 级信号：
1. 财报 EPS 超预期 / miss
2. 分析师评级变动（upgrade / downgrade）
3. 管理层指引方向
4. 需求超预期 / 供给压力 / 风险事件

去重时优先保留 TrendForce 来源的文章
"""
import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# 信号类型优先级（数字越大优先级越高）
# 用于同一 ticker 多篇新闻时取最强信号
SIGNAL_PRIORITY = {
    "beat":       5,  # 财报超预期、EPS beat
    "miss":       5,  # 财报 miss、EPS below
    "upgrade":    4,  # 评级上调
    "downgrade":  4,  # 评级下调
    "price_raise": 3, # 目标价上调
    "price_cut":  3,  # 目标价下调
    "demand_up":  2,  # 需求超预期、订单激增
    "supply_tight": 2, # 供给紧张、缺货
    "risk":       2,  # 风险事件：调查、起诉、预警
    "guidance_up": 2, # 指引上调
    "guidance_down": 2, # 指引下调
    "normal":     1,  # 正常新闻、无特殊信号
}

# 信号识别正则
SIGNAL_PATTERNS = [
    # 超预期 / miss
    (r"eps\s+beat|earnings\s+beat|profit\s+beat|q\d?\s+beat", "beat"),
    (r"beats?\s+(?:estimates?|expectations?|views?)", "beat"),
    (r"eps\s+miss|earnings\s+miss|profit\s+miss|q\d?\s+miss", "miss"),
    (r"misses?\s+(?:estimates?|expectations?|views?)", "miss"),
    # 评级变动
    (r"\brating\s+upgrade\b|\bupgrade[sd]?\b.*\brating\b|\brating\b.*\bupgrade", "upgrade"),
    (r"\brating\s+downgrade\b|\bdowngrade[sd]?\b.*\brating\b|\brating\b.*\bdowngrade", "downgrade"),
    (r"\bupgrades?\b.*\b(?:MU|SNDK|NVDA|Samsung|SK\s*hynix|Micron)", "upgrade"),
    (r"\bdowngrades?\b.*\b(?:MU|SNDK|NVDA|Samsung|SK\s*hynix|Micron)", "downgrade"),
    # 目标价变动
    (r"price\s+target.* rais|raises?\s+price\s+target|target.*上调", "price_raise"),
    (r"price\s+target.*\s+cut|lowers?\s+price\s+target|cuts?\s+price\s+target|target.*下调", "price_cut"),
    (r"(\$[\d,.]+)\s*(?:price\s+)?target", "price_raise"),  # 目标价数字出现通常意味上调
    # 需求超预期
    (r"demand\s+(?:surge|spike|exceed|远超)|(?:surge|spike)\s+in\s+demand", "demand_up"),
    (r"order(?:s)?\s+(?:surge|spike|surge|远超)", "demand_up"),
    (r"ai[-\s]driven.*demand|demand.*ai[-\s]driven", "demand_up"),
    (r"capacity\s+(?:sold?\s+out|shortage|tight)", "supply_tight"),
    (r"shortage.*(?:chip|memory|drama|supply)", "supply_tight"),
    # 供给紧张
    (r"supply\s+(?:tight|short|cut)|output\s+cut", "supply_tight"),
    (r"shortage", "supply_tight"),
    # 风险事件
    (r"investigation|probe|antitrust|lawsuit|sec\s+(?:investigation|probe)|executive\s+(?:leave|depart)|warning", "risk"),
    (r"guidance\s+(?:cut|lowered|down|miss)", "guidance_down"),
    (r"guides?\s+(?:up|higher|raise|beat|above)", "guidance_up"),
]

# 标题去重：Jaccard bigram 阈值
_DEDUP_THRESHOLD = 0.6


def _title_bigrams(title: str) -> set:
    """提取标题 bigram"""
    tokens = re.findall(r"\b\w+\b", title.lower())
    return set(zip(tokens[:-1], tokens[1:])) if len(tokens) > 1 else set()


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


def _classify_signal(title: str, summary: str = "") -> tuple:
    """
    识别文章信号类型和方向

    返回: (signal_type, display_label)
    """
    text = (title + " " + summary).lower()

    for pattern, sig_type in SIGNAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return sig_type, _signal_label(sig_type)
    return "normal", "正常"


def _signal_label(sig_type: str) -> str:
    labels = {
        "beat":        "EPS / 业绩超预期",
        "miss":        "EPS / 业绩Miss",
        "upgrade":     "评级上调",
        "downgrade":   "评级下调",
        "price_raise": "目标价上调",
        "price_cut":   "目标价下调",
        "demand_up":   "需求超预期",
        "supply_tight": "供给紧张",
        "risk":        "风险事件",
        "guidance_up": "指引上调",
        "guidance_down": "指引下调",
        "normal":      "正常",
    }
    return labels.get(sig_type, sig_type)


def _stronger_signal(a: str, b: str) -> str:
    """比较两个信号类型，返回优先级更高的那个"""
    pa = SIGNAL_PRIORITY.get(a, 0)
    pb = SIGNAL_PRIORITY.get(b, 0)
    return a if pa >= pb else b


def analyze_key_stock_news(news_articles: List[Dict]) -> Dict:
    """
    从新闻列表中提取重点公司动态信号

    输入: all_news 去重后的原始文章列表（含 category: ["key_stock"]）
    返回:
    {
        "MU": {
            "signals": [
                {"type": "upgrade", "label": "评级上调", "title": "...", "published_at": "...", "source": "..."}
            ],
            "strongest_signal": "upgrade"
        },
        ...
    }
    """
    # 按 ticker 分组
    # source 格式: "KeyStock:{name}"
    ticker_news: Dict[str, List[Dict]] = {
        "MU": [], "SNDK": [], "NVDA": [], "Samsung": [], "SK_hynix": []
    }
    ticker_map = {
        "Micron": "MU",
        "SanDisk": "SNDK",
        "NVIDIA": "NVDA",
        "Samsung": "Samsung",
        "SK hynix": "SK_hynix",
        "KeyStock:Micron": "MU",
        "KeyStock:SanDisk": "SNDK",
        "KeyStock:NVIDIA": "NVDA",
        "KeyStock:Samsung": "Samsung",
        "KeyStock:SK hynix": "SK_hynix",
    }

    for article in news_articles:
        cats = article.get("category", [])
        if cats and cats[0] == "key_stock":
            src = article.get("source", "")
            ticker = ticker_map.get(src, "")
            if ticker:
                ticker_news[ticker].append(article)

    # TrendForce 来源标记（去重优先保留）
    def is_trendforce(article: Dict) -> bool:
        src = article.get("source", "").lower()
        return "trendforce" in src or "TrendForce" in article.get("source", "")

    results = {}

    for ticker, articles in ticker_news.items():
        if not articles:
            results[ticker] = {"signals": [], "strongest_signal": "unknown"}
            continue

        # 信号提取 + 强度排序
        extracted = []
        for a in articles:
            title = a.get("title", "")
            summary = a.get("summary", "")
            sig_type, sig_label = _classify_signal(title, summary)
            extracted.append({
                "type": sig_type,
                "label": sig_label,
                "title": title,
                "published_at": a.get("published_at", ""),
                "source": a.get("source", ""),
                "is_trendforce": is_trendforce(a),
                "url": a.get("url", ""),
            })

        # 两步去重：1) TrendForce 优先 2) bigram Jaccard
        deduped = []
        for article in extracted:
            # 检查 URL 精确重复
            if any(e["url"] == article["url"] for e in deduped):
                continue
            # bigram 去重
            a_bigrams = _title_bigrams(article["title"])
            is_dup = False
            for kept in deduped:
                k_bigrams = _title_bigrams(kept["title"])
                if _jaccard(a_bigrams, k_bigrams) >= _DEDUP_THRESHOLD:
                    # URL 不同但标题高度相似：TrendForce 优先
                    if article["is_trendforce"] and not kept["is_trendforce"]:
                        deduped.remove(kept)
                        deduped.append(article)
                    else:
                        is_dup = True
                    break
            if not is_dup:
                deduped.append(article)

        # 每个 ticker 最多 3 条 evidence
        deduped = deduped[:3]

        # 取最强信号
        strongest = "unknown"
        for item in deduped:
            strongest = _stronger_signal(item["type"], strongest)

        # 同时在 trendforce 来源里找该 ticker 的信号
        # （TrendForce 抓取的文章里也有 company 信号，但 category 标记不同）
        # 这部分由 price_signal_extractor 里的 dram/nand/hbm 分类处理

        results[ticker] = {
            "signals": deduped,
            "strongest_signal": strongest,
            "strongest_label": _signal_label(strongest) if strongest != "unknown" else "未检测到信号",
        }

        logger.info(f"Key stock {ticker}: {len(deduped)} signals, strongest={strongest}")

    return results