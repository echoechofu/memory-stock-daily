"""
关键词分类与证据提取模块
"""
import os
import json
import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

# 关键词分组
DRAM_KEYWORDS = [
    "DRAM contract price", "DRAM spot price", "conventional DRAM", "server DRAM",
    "mobile DRAM", "PC DRAM", "DDR5", "LPDDR5", "DRAM shortage", "DRAM supply",
    "DRAM demand", "DRAM price hike", "DRAM ASP"
]

NAND_KEYWORDS = [
    "NAND contract price", "NAND spot price", "NAND Flash", "enterprise SSD",
    "client SSD", "eSSD", "UFS", "eMMC", "NAND shortage", "NAND supply",
    "NAND price hike", "SSD price", "SSD demand"
]

HBM_KEYWORDS = [
    "HBM", "HBM3E", "HBM4", "high bandwidth memory", "HBM shortage",
    "HBM sold out", "HBM capacity", "HBM supply", "HBM demand",
    "HBM qualification", "NVIDIA qualification", "CoWoS", "TSV", "advanced packaging"
]

CYCLE_KEYWORDS = [
    "supply tightness", "shortage", "oversupply", "inventory correction",
    "inventory days", "capacity allocation", "capacity expansion", "wafer capacity",
    "production cut", "utilization rate", "ASP", "contract price", "spot price"
]

CAPEX_KEYWORDS = [
    "CapEx", "capital expenditure", "capacity expansion", "new fab",
    "wafer starts", "equipment investment", "TSV equipment",
    "HBM capacity expansion", "oversupply risk"
]

DOWNSTREAM_KEYWORDS = [
    "AI server", "data center demand", "hyperscaler CapEx", "GPU shipment",
    "NVIDIA Blackwell", "cloud AI demand", "server shipment", "memory cost",
    "component shortage", "PC price increase", "smartphone price increase"
]

EARNINGS_KEYWORDS = [
    "EPS estimate raised", "EPS revision", "price target raised", "analyst upgrade",
    "earnings estimate", "gross margin guidance", "revenue guidance",
    "guidance raised", "guidance cut"
]


def extract_keywords_from_text(text: str, keywords: List[str]) -> List[str]:
    """从文本中提取匹配的关键词"""
    text_lower = text.lower()
    found = []
    for kw in keywords:
        if kw.lower() in text_lower:
            found.append(kw)
    return found


def extract_signals(news_articles: List[Dict]) -> Dict:
    """
    从新闻列表中提取信号并分类

    返回：
    {
      "dram": {"status": "positive", "evidence": [...]},
      "nand": {...},
      "hbm": {...},
      "capex": {...},
      "downstream": {...},
      "earnings_revision": {...}
    }
    """
    signals = {
        "dram": {"status": "unknown", "evidence": []},
        "nand": {"status": "unknown", "evidence": []},
        "hbm": {"status": "unknown", "evidence": []},
        "capex": {"status": "unknown", "evidence": []},
        "downstream": {"status": "unknown", "evidence": []},
        "earnings_revision": {"status": "unknown", "evidence": []}
    }

    # 去重：记录已处理的 URL 和高相似度标题
    seen_urls = set()
    seen_titles = []

    for article in news_articles:
        url = article.get("url", "")
        title = article.get("title", "")

        # URL 去重
        if url in seen_urls:
            continue

        # 标题相似度去重
        title_base = title.lower().strip()
        is_duplicate = False
        for existing in seen_titles:
            if levenshtein_similarity(title_base, existing) > 0.85:
                is_duplicate = True
                break

        if is_duplicate:
            continue

        seen_urls.add(url)
        seen_titles.append(title_base)

        # 提取关键词
        text_to_check = f"{title} {article.get('summary', '')}"

        matched = {}

        # DRAM
        dram_kw = extract_keywords_from_text(text_to_check, DRAM_KEYWORDS)
        if dram_kw:
            matched["dram"] = dram_kw

        # NAND
        nand_kw = extract_keywords_from_text(text_to_check, NAND_KEYWORDS)
        if nand_kw:
            matched["nand"] = nand_kw

        # HBM
        hbm_kw = extract_keywords_from_text(text_to_check, HBM_KEYWORDS)
        if hbm_kw:
            matched["hbm"] = hbm_kw

        # CapEx
        capex_kw = extract_keywords_from_text(text_to_check, CAPEX_KEYWORDS)
        if capex_kw:
            matched["capex"] = capex_kw

        # Downstream
        downstream_kw = extract_keywords_from_text(text_to_check, DOWNSTREAM_KEYWORDS)
        if downstream_kw:
            matched["downstream"] = downstream_kw

        # Earnings
        earnings_kw = extract_keywords_from_text(text_to_check, EARNINGS_KEYWORDS)
        if earnings_kw:
            matched["earnings_revision"] = earnings_kw

        # 如果有匹配，添加到证据
        if matched:
            evidence_item = {
                "title": title,
                "source": article.get("source", ""),
                "url": url,
                "published_at": article.get("published_at", ""),
                "matched_keywords": matched,
                "importance": article.get("importance", "medium")
            }

            for category in matched.keys():
                if len(signals[category]["evidence"]) < 5:
                    signals[category]["evidence"].append(evidence_item)

    # 分析状态
    for category in signals:
        evidence = signals[category]["evidence"]
        if not evidence:
            signals[category]["status"] = "unknown"
        else:
            signals[category]["status"] = analyze_status_from_evidence(evidence)

    return signals


def analyze_status_from_evidence(evidence: List[Dict]) -> str:
    """
    根据证据判断状态
    """
    positive_keywords = ["shortage", "tight", "sold out", "hike", "rising", "increase", "strong", "up"]
    negative_keywords = ["oversupply", "decline", "weak", "cut", "falling", "oversupply"]

    positive_count = 0
    negative_count = 0

    for item in evidence:
        text = f"{item.get('title', '')} {' '.join(item.get('matched_keywords', {}).get(list(item.get('matched_keywords', {}).keys())[0], []))}"
        text_lower = text.lower()

        for kw in positive_keywords:
            if kw in text_lower:
                positive_count += 1

        for kw in negative_keywords:
            if kw in text_lower:
                negative_count += 1

    if positive_count > negative_count + 1:
        return "positive"
    elif negative_count > positive_count + 1:
        return "negative"
    else:
        return "neutral"


def levenshtein_similarity(s1: str, s2: str) -> float:
    """计算两个字符串的相似度（简单版）"""
    if len(s1) == 0 or len(s2) == 0:
        return 0.0

    # 简单相似度：共同字符比例
    common = sum(1 for c in s1 if c in s2)
    return common / max(len(s1), len(s2))


def save_signals(signals: Dict, date: str):
    """保存信号到 JSON 文件"""
    output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, f"{date}_signals.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)

    logger.info(f"信号已保存到 {output_path}")
    return output_path