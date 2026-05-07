"""
TrendForce 存储价格信号抓取模块

策略：使用 Google News RSS 搜索，覆盖：
1. TrendForce 官方新闻
2. 引用 TrendForce 数据的第三方媒体（Tom's Hardware, Reuters, DRAMeXchange 等）

第三方媒体虽然摘要内容更丰富，但来源标签不是 "TrendForce"，
需要和官方文章一起抓取、统一分析。
"""
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import feedparser
import re

logger = logging.getLogger(__name__)


# ─── Google News RSS 数据源 ───
# 格式：label=显示名, url=RSS地址, trendforce_weight=是否引用TrendForce数据, category=主要类别
TRENDFORCE_SOURCES = [
    # ─── TrendForce 官方 ───
    {
        "label": "TrendForce 官方",
        "url": "https://news.google.com/rss/search?q=site:trendforce.com+memory+OR+DRAM+OR+NAND+OR+HBM&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": True,
        "importance": "high",
    },
    {
        "label": "TrendForce DRAM",
        "url": "https://news.google.com/rss/search?q=site:trendforce.com+DRAM+contract+price&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": True,
        "importance": "high",
    },
    {
        "label": "TrendForce NAND",
        "url": "https://news.google.com/rss/search?q=site:trendforce.com+NAND+flash+price&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": True,
        "importance": "high",
    },
    {
        "label": "TrendForce HBM",
        "url": "https://news.google.com/rss/search?q=site:trendforce.com+HBM+high+bandwidth&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": True,
        "importance": "high",
    },
    # ─── DRAM 价格（包含第三方媒体，这些摘要有实际数字）───
    {
        "label": "DRAM价格",
        "url": "https://news.google.com/rss/search?q=TrendForce+DRAM+contract+price+quarterly&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": True,
        "importance": "high",
    },
    # ─── NAND 价格 ───
    {
        "label": "NAND价格",
        "url": "https://news.google.com/rss/search?q=TrendForce+NAND+flash+price+contract&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": True,
        "importance": "high",
    },
    # ─── HBM 供需 ───
    {
        "label": "HBM供需",
        "url": "https://news.google.com/rss/search?q=HBM+high+bandwidth+memory+supply+demand+TrendForce&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": True,
        "importance": "high",
    },
    # ─── 通用 HBM（捕捉非 TrendForce 官方的 HBM 需求文章）───
    {
        "label": "HBM通用",
        "url": "https://news.google.com/rss/search?q=HBM+memory+demand+supply+shortage+sold+out&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": False,
        "importance": "high",
    },
    # ─── 存储市场综合 ───
    {
        "label": "存储市场",
        "url": "https://news.google.com/rss/search?q=memory+chip+DRAM+NAND+price+outlook+2026&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": False,
        "importance": "medium",
    },
    # ─── AI Server DRAM 需求 ───
    {
        "label": "AI服务器存储",
        "url": "https://news.google.com/rss/search?q=AI+server+DRAM+HBM+memory+demand+supply&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": False,
        "importance": "medium",
    },
    # ─── 存储短缺/供给 ───
    {
        "label": "存储短缺",
        "url": "https://news.google.com/rss/search?q=memory+DRAM+NAND+shortage+supply+tight+price+surge&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": False,
        "importance": "medium",
    },
    # ─── Reuters / Tom's Hardware / Businesskorea 等高价值媒体 ───
    {
        "label": "Tom's Hardware DRAM",
        "url": "https://news.google.com/rss/search?q=site:tomshardware.com+DRAM+memory+price+TrendForce&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": True,
        "importance": "high",
    },
    {
        "label": "Reuters DRAM",
        "url": "https://news.google.com/rss/search?q=site:reuters.com+DRAM+NAND+memory+price+TrendForce&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": True,
        "importance": "high",
    },
    {
        "label": "Businesskorea存储",
        "url": "https://news.google.com/rss/search?q=site:businesskorea.co.kr+DRAM+NAND+TrendForce+price&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": True,
        "importance": "high",
    },
    {
        "label": "DRAMeXchange",
        "url": "https://news.google.com/rss/search?q=site:dramxchange.com+DRAM+NAND+memory+price&hl=en&gl=US&ceid=US:en",
        "trendforce_cite": True,
        "importance": "high",
    },
]


def _extract_source_name(entry) -> str:
    """从 RSS 条目中提取来源名称"""
    title = entry.get("title", "")
    # 通常格式: "Article Title - SourceName"
    parts = title.rsplit(" - ", 1)
    if len(parts) > 1:
        return parts[-1].strip()
    # source 可能是 FeedParserDict {'href': url, 'title': name}
    raw_source = entry.get("source", "")
    if isinstance(raw_source, dict):
        return raw_source.get("title", "") or ""
    return str(raw_source) if raw_source else ""


def _is_memory_related_article(title: str, summary: str) -> bool:
    """判断文章是否与存储股相关"""
    text = (title + " " + summary).lower()
    memory_keywords = [
        "dram", "nand", "flash", "ssd", "hbm", "memory chip",
        "lpddr", "ddr4", "ddr5", "gddr",
        "memory price", "memory contract", "memory supply",
        "memory demand", "memory shortage", "server memory",
        "storage chip", "solid state"
    ]
    return any(kw in text for kw in memory_keywords)


def _classify_article(title: str, summary: str) -> Dict:
    """分类文章并提取关键词"""
    text = (title + " " + summary).lower()

    categories = []
    is_memory = False

    if any(k in text for k in ["dram", "ddr4", "ddr5", "lpddr", "gddr", "server dram", "mobile dram", "specialty dram"]):
        categories.append("dram")
        is_memory = True
    if any(k in text for k in ["nand", "flash", "ssd", "3d nand", "qlc", "tlc"]):
        categories.append("nand")
        is_memory = True
    if any(k in text for k in ["hbm", "hbm2", "hbm3", "hbm3e", "hbm4", "hbms", "high bandwidth memory"]):
        categories.append("hbm")
        is_memory = True
    if any(k in text for k in ["server dram", "enterprise ssd", "ai server", "data center", "cloud"]):
        categories.append("downstream")
    if any(k in text for k in ["capacity", "supply", "production", "fab", "utilization", "capex", "expansion", "shortage"]):
        categories.append("capex")
    if any(k in text for k in ["eps", "guidance", "forecast", "outlook", "revision", "analyst", "earning"]):
        categories.append("earnings_revision")

    return {"categories": list(set(categories)), "is_memory_related": is_memory}


def _clean_html(text: str) -> str:
    """清理 HTML 标签"""
    return re.sub(r"<[^>]+>", "", text).strip()


def fetch_trendforce_news(max_articles_per_source: int = 30, retention_days: int = 30) -> List[Dict]:
    """
    抓取 TrendForce 及引用 TrendForce 的存储价格相关新闻

    返回结构：
    [
      {
        "source": "Tom's Hardware" / "TrendForce" / "Reuters" 等,
        "source_label": "DRAM价格",
        "title": "...",
        "url": "...",
        "published_at": "...",
        "summary": "...",
        "raw_text": "...",
        "category": ["dram", "nand"],
        "importance": "high",
        "price_signal": "up"/"down"/"neutral"/"unknown",
        "trendforce_cite": True/False
      }
    ]
    """
    articles = []
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    seen_titles = set()

    for source_config in TRENDFORCE_SOURCES:
        url = source_config["url"]
        label = source_config["label"]
        importance = source_config.get("importance", "medium")
        trendforce_cite = source_config.get("trendforce_cite", False)

        try:
            feed = feedparser.parse(url)
            logger.info(f"[TrendForce] {label}: 获取 {len(feed.entries)} 条")

            for entry in feed.entries[:max_articles_per_source]:
                try:
                    title = entry.get("title", "").strip()
                    if not title:
                        continue

                    # 标题去重
                    title_key = title.lower()
                    if title_key in seen_titles:
                        continue

                    # 解析日期
                    published_at = ""
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            pub_dt = datetime(*entry.published_parsed[:6])
                            published_at = pub_dt.strftime("%Y-%m-%d")
                            if pub_dt < cutoff_date:
                                continue
                        except Exception:
                            pass

                    # 摘要
                    summary = ""
                    for field in ["summary", "description", "content"]:
                        raw = entry.get(field, "")
                        if raw:
                            summary = _clean_html(str(raw))
                            break

                    # 提取来源名称
                    source_name = _extract_source_name(entry)
                    if not source_name:
                        source_name = entry.get("source", "")
                        if hasattr(source_name, "title"):
                            source_name = source_name.title or ""

                    # 判断是否存储相关
                    classification = _classify_article(title, summary)
                    if not classification["is_memory_related"]:
                        # 只要标题有存储关键词就保留
                        if not _is_memory_related_article(title, summary):
                            continue

                    # 提取价格信号
                    price_signal = _extract_price_signal(title + " " + summary)

                    raw_text = title + " " + summary
                    seen_titles.add(title_key)

                    articles.append({
                        "source": source_name or "TrendForce",
                        "source_label": label,
                        "title": title,
                        "url": entry.get("link", ""),
                        "published_at": published_at,
                        "summary": summary[:300],
                        "raw_text": raw_text,
                        "category": classification["categories"] or ["dram"],
                        "importance": importance,
                        "price_signal": price_signal,
                        "trendforce_cite": trendforce_cite,
                    })

                except Exception as e:
                    logger.warning(f"[TrendForce] 解析文章失败 [{label}]: {e}")
                    continue

        except Exception as e:
            logger.error(f"[TrendForce] RSS 抓取失败 [{label}]: {e}")
            continue

    logger.info(f"[TrendForce] 共获取 {len(articles)} 篇唯一文章（去重后）")
    return articles


def _extract_price_signal(text: str) -> str:
    """从文本提取价格方向信号（使用词边界避免 slowdown 等误判）"""
    text_lower = text.lower()

    # 上涨信号：使用词边界匹配
    up_patterns = [
        r"\brise[s]?\b", r"\brising\b", r"\bincrease[s]?\b", r"\bincreasing\b",
        r"\bsurge[s]?\b", r"\bsurging\b", r"\bjump[s]?\b", r"\bjumping\b",
        r"\bclimb[s]?\b", r"\bclimbing\b", r"\bgain[s]?\b", r"\bgains\b",
        r"\bupturn\b", r"\bsoar[s]?\b", r"\bsoaring\b", r"\bhigher\b",
        r"\+(\d+(?:\.\d+)?)\s*%",  # +48%
    ]
    for pat in up_patterns:
        if re.search(pat, text_lower):
            return "up"

    # 下跌信号：使用词边界匹配（避免 slowdown, countdown 等误判）
    down_patterns = [
        r"\bfall(?:s|ing)?\b", r"\bdrop(?:s|ped|ping)?\b",
        r"\bdecline[s]?\b", r"\bdecreasing\b", r"\bplunge[s]?\b",
        r"\bplunging\b", r"\bcrash(?:ed|ing)?\b", r"\bdownturn\b",
        r"-(\d+(?:\.\d+)?)\s*%",  # -10%
    ]
    for pat in down_patterns:
        if re.search(pat, text_lower):
            return "down"

    return "neutral"
