"""
公司 IR 新闻抓取模块
"""
import os
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests
import feedparser

logger = logging.getLogger(__name__)


def fetch_company_ir_news(company: str) -> List[Dict]:
    """
    获取公司 IR 新闻

    支持：
    - Micron
    - SanDisk
    - NVIDIA
    - Samsung
    - SK hynix
    """
    ir_sources = {
        "micron": {
            "name": "Micron",
            "ir_url": "https://investors.micron.com/news",
            "rss_url": "https://investors.micron.com/news/rss"
        },
        "nvidia": {
            "name": "NVIDIA",
            "ir_url": "https://investor.nvidia.com",
            "rss_url": "https://investor.nvidia.com/rss/news.rss"
        },
        "samsung": {
            "name": "Samsung",
            "ir_url": "https://www.samsung.com/global/ir/news/news.do"
        },
        "sk_hynix": {
            "name": "SK hynix",
            "ir_url": "https://www.skhynix.com/english/ir/news/press.do"
        },
        "western_digital": {
            "name": "Western Digital",
            "ir_url": "https://www.westerndigital.com/en-us/investors"
        }
    }

    company_key = company.lower().replace(" ", "_").replace("-", "_")
    config = ir_sources.get(company_key)

    if not config:
        logger.warning(f"Unknown company: {company}")
        return []

    articles = []

    # 尝试 RSS
    if "rss_url" in config:
        rss_articles = fetch_ir_rss(config["rss_url"], config["name"])
        articles.extend(rss_articles)

    # 如果没有RSS，尝试抓取网页
    if not articles:
        web_articles = fetch_ir_webpage(config["ir_url"], config["name"])
        articles.extend(web_articles)

    return articles


def fetch_ir_rss(rss_url: str, company_name: str) -> List[Dict]:
    """
    通过 RSS 获取 IR 新闻
    """
    articles = []

    try:
        feed = feedparser.parse(rss_url)

        for entry in feed.entries[:15]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", "")
            summary = entry.get("summary", "") or entry.get("description", "")

            if summary:
                summary = re.sub(r'<[^>]+>', '', summary)
                summary = summary.strip()

            articles.append({
                "company": company_name,
                "source": f"{company_name} IR",
                "title": title,
                "url": link,
                "published_at": published,
                "summary": summary[:500],
                "matched_keywords": extract_ir_keywords(title + " " + summary),
                "category": [],
                "importance": "high"
            })

    except Exception as e:
        logger.error(f"IR RSS fetch failed for {company_name}: {e}")

    return articles


def fetch_ir_webpage(ir_url: str, company_name: str) -> List[Dict]:
    """
    直接抓取 IR 网页
    """
    articles = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        response = requests.get(ir_url, headers=headers, timeout=30)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.content, "lxml")

        # 尝试找新闻列表项
        news_items = soup.find_all("div", class_="news-item") or soup.find_all("li", class_="news")

        for item in news_items[:15]:
            title_elem = item.find("h3") or item.find("h4") or item.find("a")
            date_elem = item.find("span", class_="date") or item.find("time")
            link_elem = item.find("a")

            if title_elem:
                title = title_elem.get_text(strip=True)
                link = link_elem.get("href", "") if link_elem else ir_url

                if link and not link.startswith("http"):
                    if link.startswith("/"):
                        base = "/".join(ir_url.split("/")[:3])
                        link = base + link
                    else:
                        link = ir_url + "/" + link

                articles.append({
                    "company": company_name,
                    "source": f"{company_name} IR",
                    "title": title,
                    "url": link,
                    "published_at": date_elem.get_text(strip=True) if date_elem else "",
                    "summary": "",
                    "matched_keywords": extract_ir_keywords(title),
                    "category": [],
                    "importance": "high"
                })

    except Exception as e:
        logger.error(f"IR webpage fetch failed for {company_name}: {e}")

    return articles


def extract_ir_keywords(text: str) -> List[str]:
    """
    从 IR 文本中提取关键词
    """
    keywords = [
        "HBM", "HBM3E", "HBM4", "DRAM", "NAND", "NAND Flash",
        "revenue", "guidance", "gross margin", "EPS",
        "AI server", "data center", "capacity", "supply",
        "memory", "semiconductor", "enterprise SSD"
    ]

    found = []
    text_lower = text.lower()

    for kw in keywords:
        if kw.lower() in text_lower:
            found.append(kw)

    return found


def fetch_all_company_news() -> List[Dict]:
    """
    获取所有公司的 IR 新闻
    """
    companies = ["Micron", "NVIDIA", "Samsung", "SK hynix", "Western Digital"]
    all_articles = []

    for company in companies:
        articles = fetch_company_ir_news(company)
        all_articles.extend(articles)

    return all_articles