"""
相对强弱计算模块
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def calculate_relative_strength(market_signals: Dict) -> Dict:
    """
    计算相对强弱指标

    返回：
    {
      "MU": {
        "vs_SOXX_5d": 4.3,
        "vs_SOXX_20d": 12.6,
        "vs_NVDA_5d": 2.0,
        "strength": "strong" | "weak" | "neutral"
      }
    }
    """
    results = {}

    tickers = list(market_signals.keys())

    for ticker in tickers:
        if ticker == "SOXX" or ticker == "SMH":
            continue

        ticker_data = market_signals.get(ticker, {})
        result = {
            "vs_SOXX_5d": None,
            "vs_SOXX_20d": None,
            "vs_NVDA_5d": None,
            "strength": "neutral"
        }

        # 计算 vs SOXX
        soxx_data = market_signals.get("SOXX", {})
        if soxx_data:
            ticker_5d = ticker_data.get("five_day_change_pct", 0)
            soxx_5d = soxx_data.get("five_day_change_pct", 0)
            ticker_20d = ticker_data.get("twenty_day_change_pct", 0)
            soxx_20d = soxx_data.get("twenty_day_change_pct", 0)

            result["vs_SOXX_5d"] = round(ticker_5d - soxx_5d, 2)
            result["vs_SOXX_20d"] = round(ticker_20d - soxx_20d, 2)

        # 计算 vs NVDA
        nvda_data = market_signals.get("NVDA", {})
        if nvda_data and ticker != "NVDA":
            ticker_5d = ticker_data.get("five_day_change_pct", 0)
            nvda_5d = nvda_data.get("five_day_change_pct", 0)
            result["vs_NVDA_5d"] = round(ticker_5d - nvda_5d, 2)

        # 判断强弱
        positive_count = 0
        if result["vs_SOXX_5d"] and result["vs_SOXX_5d"] > 0:
            positive_count += 1
        if result["vs_SOXX_20d"] and result["vs_SOXX_20d"] > 0:
            positive_count += 1
        if result["vs_NVDA_5d"] and result["vs_NVDA_5d"] > 0:
            positive_count += 1

        if positive_count >= 2:
            result["strength"] = "strong"
        elif positive_count == 0:
            result["strength"] = "weak"

        results[ticker] = result

    return results


def format_relative_strength_table(relative_strength: Dict) -> str:
    """
    格式化相对强弱表格
    """
    lines = []
    lines.append("| 股票 | vs SOXX 5日 | vs SOXX 20日 | vs NVDA 5日 | 强弱 |")
    lines.append("|------|-------------|-------------|------------|------|")

    for ticker, data in relative_strength.items():
        vs_soxx_5d = f"{data['vs_SOXX_5d']:+.2f}%" if data['vs_SOXX_5d'] is not None else "-"
        vs_soxx_20d = f"{data['vs_SOXX_20d']:+.2f}%" if data['vs_SOXX_20d'] is not None else "-"
        vs_nvda_5d = f"{data['vs_NVDA_5d']:+.2f}%" if data['vs_NVDA_5d'] is not None else "-"

        strength_emoji = "↑" if data["strength"] == "strong" else ("↓" if data["strength"] == "weak" else "→")

        lines.append(f"| {ticker} | {vs_soxx_5d} | {vs_soxx_20d} | {vs_nvda_5d} | {strength_emoji} |")

    return "\n".join(lines)