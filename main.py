"""
存储股日报系统 - 主程序
每天定时运行，生成日报并推送到 Telegram
"""
import os
import re
import json
import logging
from datetime import datetime, date
from typing import Dict, List
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("memory-watch.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


# ─── 去重函数 ────────────────────────────────────────────────────────────────

def _strip_source_suffix(title: str) -> str:
    """去掉标题末尾的 ' - 来源名' 后缀"""
    return re.sub(r"\s+-\s+[^—\-]+(\s*-[^—\-]+)*\s*$", "", title).strip()


def _title_bigrams(title: str) -> set:
    """提取标题的 bigram 集合（按词边界分词）"""
    clean = _strip_source_suffix(title).lower()
    tokens = re.findall(r"\b\w+\b", clean)
    return set(zip(tokens[:-1], tokens[1:])) if len(tokens) > 1 else set()


def _jaccard_bigrams(bigrams1: set, bigrams2: set) -> float:
    """两个 bigram 集合的 Jaccard 相似度"""
    if not bigrams1 or not bigrams2:
        return 0.0
    inter = len(bigrams1 & bigrams2)
    union = len(bigrams1 | bigrams2)
    return inter / union if union > 0 else 0.0


def _deduplicate_articles(articles: List[Dict], sim_threshold: float = 0.6) -> List[Dict]:
    """
    两层去重：
    1. URL 精确去重（优先）
    2. 标题 Bigram Jaccard 相似度去重（阈值默认 0.6）
    """
    # 第一层：URL 去重
    seen_urls = set()
    url_deduped = []
    for a in articles:
        url = a.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            url_deduped.append(a)

    # 第二层：标题 bigram Jaccard 去重
    kept = []
    for a in url_deduped:
        title = a.get("title", "")
        a_bigrams = _title_bigrams(title)
        is_duplicate = False
        for kept_a in kept:
            k_bigrams = _title_bigrams(kept_a.get("title", ""))
            if _jaccard_bigrams(a_bigrams, k_bigrams) >= sim_threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            kept.append(a)

    dropped = len(articles) - len(kept)
    if dropped > 0:
        logger.info(f"去重完成：原始 {len(articles)} 篇 → 去重后 {len(kept)} 篇（去掉 {dropped} 篇重复）")
    return kept


# ─── 成交量放量判断 ─────────────────────────────────────────────────────────

def _volume_flag(vol: float, vol_5d: float, vol_20d: float) -> str:
    """
    判断成交量是否超过 5日/20日均量的 2 倍，返回标注字符串。
    只在超过 2 倍阈值时才返回非空字符串。
    """
    flags = []
    if vol_5d > 0 and vol >= vol_5d * 2:
        flags.append(f"成交量超 5 日均 {vol/vol_5d:.1f} 倍")
    if vol_20d > 0 and vol >= vol_20d * 2:
        flags.append(f"成交量超 20 日均 {vol/vol_20d:.1f} 倍")
    return " | ".join(flags)


def run_daily_report():
    """
    执行每日日报生成流程
    """
    today = date.today().isoformat()
    logger.info(f"===== 开始生成 {today} 存储股日报 =====")

    results = {
        "date": today,
        "quotes": None,
        "news": None,
        "signals": None,
        "score": None,
        "report": None,
        "errors": []
    }

    # ==== Step 1: 获取行情数据 ====
    logger.info("Step 1: 获取行情数据")
    try:
        from sources.futu_quotes import calculate_market_signals, save_quotes

        tickers = ["MU", "SNDK", "NVDA", "SOXX", "SMH"]
        market_signals = calculate_market_signals(tickers)

        if market_signals:
            save_quotes(market_signals, today)
            results["quotes"] = market_signals
            logger.info(f"行情数据获取成功：{list(market_signals.keys())}")
        else:
            logger.warning("行情数据获取失败或为空")
            results["errors"].append("行情数据获取失败")

    except Exception as e:
        logger.error(f"行情模块异常：{e}")
        results["errors"].append(f"行情模块: {str(e)}")

    # ==== Step 2: 获取新闻数据 ====
    logger.info("Step 2: 获取新闻数据")

    all_news = []

    # TrendForce 新闻
    try:
        from sources.trendforce import fetch_trendforce_news
        trendforce_news = fetch_trendforce_news()
        all_news.extend(trendforce_news)
        logger.info(f"TrendForce 获取 {len(trendforce_news)} 篇")
    except Exception as e:
        logger.error(f"TrendForce 抓取失败：{e}")
        results["errors"].append(f"TrendForce: {str(e)}")

    # 通用新闻（含重点股票、大宗商品、美元）
    try:
        from sources.news import fetch_memory_news
        memory_news = fetch_memory_news()
        all_news.extend(memory_news)
        logger.info(f"通用新闻获取 {len(memory_news)} 篇")
    except Exception as e:
        logger.error(f"新闻模块失败：{e}")
        results["errors"].append(f"新闻模块: {str(e)}")

    results["news"] = all_news
    logger.info(f"新闻总计 {len(all_news)} 篇（含两个来源，尚未去重）")

    # 保存原始新闻
    if all_news:
        raw_dir = os.path.join(os.path.dirname(__file__), "data", "raw")
        os.makedirs(raw_dir, exist_ok=True)
        news_path = os.path.join(raw_dir, f"{today}_news.json")
        with open(news_path, "w", encoding="utf-8") as f:
            json.dump(all_news, f, ensure_ascii=False, indent=2)
        logger.info(f"新闻已保存到 {news_path}")

    # ── 新闻去重 ──
    all_news = _deduplicate_articles(all_news)
    results["news"] = all_news
    logger.info(f"去重后新闻 {len(all_news)} 篇")

    # ==== Step 3: 提取信号（新：正则价格信号） ====
    logger.info("Step 3: 提取信号")
    try:
        from sources.price_signal_extractor import extract_signals_from_articles
        from analysis.signal_extractor import save_signals

        extracted_signals = extract_signals_from_articles(all_news)
        results["signals"] = extracted_signals
        save_signals(extracted_signals, today)
        logger.info("信号提取完成")
    except Exception as e:
        logger.error(f"信号提取失败：{e}")
        results["errors"].append(f"信号提取: {str(e)}")
        extracted_signals = {"dram": {}, "nand": {}, "hbm": {}, "capex": {}, "downstream": {}, "earnings_revision": {}, "all_signals": []}

    # ==== Step 4: 计算评分 ====
    logger.info("Step 4: 计算评分")
    try:
        from analysis.scoring import calculate_score, extract_risk_signals

        market_signals = results.get("quotes") or {}
        score_result = calculate_score(market_signals, extracted_signals)
        results["score"] = score_result

        risk_signals = extract_risk_signals(all_news, extracted_signals)
        logger.info(f"评分：{score_result['total_score']}/5，状态：{score_result['status']}")
        logger.info(f"风险信号：{len(risk_signals)} 条")
    except Exception as e:
        logger.error(f"评分计算失败：{e}")
        results["errors"].append(f"评分计算: {str(e)}")
        score_result = {"total_score": 0, "status": "unknown", "scores": {}, "reasons": {}}
        risk_signals = []

    # ==== Step 5: 生成日报 ====
    logger.info("Step 5: 生成日报")

    input_data = {
        "date": today,
        "market_signals": results.get("quotes", {}),
        "signals": extracted_signals,
        "score": score_result,
        "risk_signals": risk_signals,
        "news_count": len(all_news)
    }

    try:
        from llm.minimax_client import generate_daily_report, save_report

        report = generate_daily_report(input_data, "prompts/daily_memory_report.md")

        if report:
            results["report"] = report
            save_report(report, today)
            logger.info("日报生成成功")
        else:
            logger.warning("MiniMax API 失败，使用备选格式")
            results["errors"].append("MiniMax API 调用失败")
            report = generate_fallback_report(input_data)
            results["report"] = report
            save_report(report, today)

    except Exception as e:
        logger.error(f"日报生成失败：{e}")
        results["errors"].append(f"日报生成: {str(e)}")
        report = generate_fallback_report(input_data)
        results["report"] = report

    # ==== Step 6: 推送 ====
    logger.info("Step 6: 推送")
    try:
        from push.telegram import send_telegram_with_retry, notify_error

        if report:
            success = send_telegram_with_retry(report)
            if success:
                logger.info("Telegram 推送成功")
            else:
                logger.warning("Telegram 推送失败（本地报告已保存）")
    except Exception as e:
        logger.error(f"Telegram 推送异常：{e}")

    # 错误通知
    if results["errors"]:
        try:
            from push.telegram import notify_error
            error_msg = f"日报生成完成，但有 {len(results['errors'])} 个错误：\n" + "\n".join(results["errors"])
            notify_error(error_msg)
        except:
            pass

    logger.info(f"===== {today} 日报生成完成 =====")
    return results


def generate_fallback_report(input_data: Dict) -> str:
    """
    MiniMax 失败时，生成简单的备选报告
    """
    today = input_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    score = input_data.get("score", {})
    market = input_data.get("market_signals") or {}
    signals = input_data.get("signals", {})

    lines = []
    lines.append(f"【存储股日报｜{today}】")
    lines.append("")
    lines.append(f"今日评分：{score.get('total_score', '?')}/5")
    lines.append(f"状态：{score.get('status', 'unknown')}")
    lines.append("")

    # 行情（含成交量）
    lines.append("【行情】")
    for ticker, data in market.items():
        price = data.get("latest_price", 0)
        change = data.get("daily_change_pct", 0)
        change_5d = data.get("five_day_change_pct", 0)
        change_20d = data.get("twenty_day_change_pct", 0)
        vol = data.get("volume", 0)
        vol_5d = data.get("volume_5d_avg", 0)
        vol_20d = data.get("volume_20d_avg", 0)

        vol_wan = vol / 10000 if vol > 0 else 0
        vol_5d_wan = vol_5d / 10000 if vol_5d > 0 else 0
        vol_20d_wan = vol_20d / 10000 if vol_20d > 0 else 0

        price_5d_avg = data.get("price_5d_avg", 0)
        price_20d_avg = data.get("price_20d_avg", 0)
        lines.append(
            f"- {ticker}: ${price:.2f} ({change:+.2f}%) | "
            f"5日 {change_5d:+.2f}% | 20日 {change_20d:+.2f}% | "
            f"成交量 {vol_wan:.0f}万（5日均 {vol_5d_wan:.0f}万 / 20日均 {vol_20d_wan:.0f}万）| "
            f"5日均价 ${price_5d_avg:.2f} | 20日均价 ${price_20d_avg:.2f}"
        )

        vol_alert = _volume_flag(vol, vol_5d, vol_20d)
        if vol_alert:
            lines.append(f"  ⚠️ {vol_alert}")

    lines.append("")

    # 信号状态（含发布时间）
    lines.append("【信号】")
    for category in ["dram", "nand", "hbm", "capex", "downstream"]:
        cat_data = signals.get(category, {})
        status = cat_data.get("status", "unknown")
        evidence_list = cat_data.get("evidence", [])
        lines.append(f"- {category.upper()}: {status} ({len(evidence_list)} 条证据)")
        for ev in evidence_list[:3]:
            pub = ev.get("published_at", "")
            pub_str = f" [{pub}]" if pub else ""
            title_short = ev.get("title", "")[:70]
            direction = ev.get("direction", "")
            dir_str = f"[{direction}] " if direction and direction != "unknown" else ""
            lines.append(f"  {dir_str}{title_short}{pub_str}")
    lines.append("")

    lines.append("⚠️ MiniMax API 调用失败，查看 data/raw 目录获取原始数据。")

    return "\n".join(lines)


if __name__ == "__main__":
    run_daily_report()