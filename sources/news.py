"""
通用新闻抓取模块 - Yahoo Finance RSS, Tom's Hardware, 宏观大宗, 重点股票新闻
"""
import os
import re
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests
import feedparser
import email.utils

logger = logging.getLogger(__name__)

# 30天时效过滤
DAYS_30 = 30


def _parse_date(published: str) -> Optional[datetime]:
    """解析 RSS feed 的日期字符串，返回 datetime 或 None（解析失败时）"""
    if not published:
        return None
    # 常见 RSS 日期格式：RFC 822 / RFC 1123
    parsed = email.utils.parsedate_tz(published)
    if parsed:
        try:
            from email.utils import mktime_tz
            return datetime.fromtimestamp(mktime_tz(parsed))
        except Exception:
            pass
    # 备选：Try common formats
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(published[:22], fmt)
        except Exception:
            pass
    return None


def _is_recent(published: str) -> bool:
    """判断新闻是否在30天以内"""
    dt = _parse_date(published)
    if dt is None:
        return True  # 解析不了就保留
    now = datetime.now()
    # 确保 now 是 offset-naive 以便比较
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None) - dt.utcoffset()
        now = datetime.now()
    cutoff = now - timedelta(days=DAYS_30)
    return dt >= cutoff


def _clean_summary(summary: str) -> str:
    """清洗 HTML 标签并截断摘要"""
    if not summary:
        return ""
    text = re.sub(r'<[^>]+>', '', summary).strip()
    return text[:500]


def fetch_memory_news() -> List[Dict]:
    """
    通过关键词搜索抓取存储相关新闻 + 宏观大宗 + 重点股票新闻

    关键词范围：
    - Micron HBM, Micron DRAM price, Micron NAND price
    - SanDisk NAND price
    - SK hynix HBM, Samsung HBM
    - HBM shortage, DRAM contract price, NAND contract price
    - server DRAM, enterprise SSD, memory shortage, memory price hike

    宏观：黄金 / WTI 原油 / 美元指数
    重点股票：MU, SNDK, NVDA, Samsung, SK hynix
    """
    articles = []

    # Yahoo Finance RSS
    yahoo_articles = fetch_yahoo_finance_rss()
    articles.extend(yahoo_articles)

    # Tom's Hardware（存储相关）
    toms_articles = fetch_tomshardware_news()
    articles.extend(toms_articles)

    # 宏观大宗 + 美元（Google News RSS 搜索）
    macro_articles = fetch_macro_news()
    articles.extend(macro_articles)

    # 重点股票新闻（MU / SNDK / NVDA / Samsung / SK hynix）
    stock_articles = fetch_key_stocks_news()
    articles.extend(stock_articles)

    return articles


def fetch_yahoo_finance_rss() -> List[Dict]:
    """
    获取 Yahoo Finance RSS 新闻（30天时效）
    """
    articles = []
    rss_url = "https://finance.yahoo.com/news/rss"

    try:
        feed = feedparser.parse(rss_url)

        for entry in feed.entries[:20]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", "")
            summary = entry.get("summary", "")

            # 30天时效过滤
            if not _is_recent(published):
                continue

            # 清洗HTML标签
            summary = _clean_summary(summary)

            articles.append({
                "source": "Yahoo Finance",
                "title": title,
                "url": link,
                "published_at": published,
                "summary": summary[:500],  # 截断过长摘要
                "raw_text": summary,
                "matched_keywords": extract_keywords_from_text(title + " " + summary),
                "category": [],
                "importance": "medium"
            })

    except Exception as e:
        logger.error(f"Yahoo Finance RSS fetch failed: {e}")

    return articles


def fetch_tomshardware_news() -> List[Dict]:
    """
    获取 Tom's Hardware 存储相关新闻（30天时效）
    """
    articles = []
    base_url = "https://www.tomshardware.com"

    # 存储相关RSS
    rss_url = "https://www.tomshardware.com/feeds/rss/all.xml"

    try:
        feed = feedparser.parse(rss_url)

        keywords = ["memory", "DRAM", "NAND", "SSD", "HBM", "Micron", "Samsung", "SK hynix", "SanDisk"]

        for entry in feed.entries[:50]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", "")
            summary = entry.get("summary", "")

            # 30天时效过滤
            if not _is_recent(published):
                continue

            # 只保留包含存储关键词的文章
            if not any(kw.lower() in title.lower() + summary.lower() for kw in keywords):
                continue

            # 清洗HTML
            summary = _clean_summary(summary)

            articles.append({
                "source": "Tom's Hardware",
                "title": title,
                "url": link,
                "published_at": published,
                "summary": summary,
                "raw_text": summary,
                "matched_keywords": extract_keywords_from_text(title + " " + summary),
                "category": [],
                "importance": "medium"
            })

    except Exception as e:
        logger.error(f"Tom's Hardware RSS fetch failed: {e}")

    return articles


def fetch_macro_news() -> List[Dict]:
    """
    抓取宏观大宗（黄金、WTI原油、美元）最新走势新闻，30天时效
    """
    articles = []
    keywords = [
        "gold price", "XAU USD", "WTI crude oil", "crude oil price",
        "USD index", "dollar strength", "DXY"
    ]
    for kw in keywords:
        results = search_news_by_keyword(kw, max_results=5)
        for a in results:
            a["source"] = "Macro"
            a["category"] = ["macro"]
        articles.extend(results)
    return articles


def fetch_key_stocks_news() -> List[Dict]:
    """
    抓取重点存储股（MU/SNDK/NVDA/Samsung/SK hynix）新闻，30天时效
    """
    articles = []
    tickers = [
        ("MU", "Micron"),
        ("SNDK", "SanDisk"),
        ("NVDA", "NVIDIA"),
        ("Samsung semiconductor", "Samsung"),
        ("SK hynix", "SK hynix"),
    ]
    for ticker, name in tickers:
        results = search_news_by_keyword(ticker, max_results=5)
        for a in results:
            a["source"] = f"KeyStock:{name}"
            a["category"] = ["key_stock"]
        articles.extend(results)
    return articles


def extract_keywords_from_text(text: str) -> List[str]:
    """
    从文本中提取关键词
    """
    keywords = [
        "DRAM contract price", "DRAM spot price", "server DRAM", "mobile DRAM",
        "NAND contract price", "NAND spot price", "enterprise SSD", "client SSD",
        "HBM", "HBM3E", "HBM4", "HBM shortage", "HBM sold out",
        "memory shortage", "memory price hike", "supply tightness", "oversupply",
        "AI server", "data center demand", "GPU shipment", "NVIDIA Blackwell",
        "CapEx", "capacity expansion", "new fab", "oversupply risk"
    ]

    found = []
    text_lower = text.lower()

    for kw in keywords:
        if kw.lower() in text_lower:
            found.append(kw)

    return found


def search_news_by_keyword(keyword: str, max_results: int = 10) -> List[Dict]:
    """
    通过 Google News RSS 搜索特定关键词的新闻
    """
    articles = []
    search_url = f"https://news.google.com/rss/search?q={requests.utils.quote(keyword)}&hl=en-US&gl=US&ceid=US:en"

    try:
        feed = feedparser.parse(search_url)

        for entry in feed.entries[:max_results]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", "")
            summary = entry.get("summary", "")

            # 30天时效过滤
            if not _is_recent(published):
                continue

            if summary:
                summary = re.sub(r'<[^>]+>', '', summary)

            articles.append({
                "source": "Google News",
                "title": title,
                "url": link,
                "published_at": published,
                "summary": summary[:500],
                "matched_keywords": [keyword],
                "category": [],
                "importance": "medium"
            })

    except Exception as e:
        logger.error(f"Google News search for '{keyword}' failed: {e}")

    return articles