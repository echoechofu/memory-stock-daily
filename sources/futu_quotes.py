"""
富途行情模块 - 获取存储股每日行情数据
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def fetch_daily_quote(ticker: str) -> Optional[Dict]:
    """
    获取单个股票的最新行情
    """
    try:
        import futu

        host = os.getenv("FUTU_HOST", "127.0.0.1")
        port = int(os.getenv("FUTU_PORT", "11111"))

        quote_ctx = futu.OpenQuoteContext(host=host, port=port)

        ret, data = quote_ctx.get_stock_quote([ticker])
        if ret != 0:
            logger.error(f"Failed to get quote for {ticker}: {data}")
            return None

        quote_ctx.close()

        if data is not None and len(data) > 0:
            row = data.iloc[0]
            return {
                "ticker": ticker,
                "latest_price": float(row.get("last_price", 0)),
                "daily_change_pct": float(row.get("change_rate", 0)),
                "volume": int(row.get("volume", 0)),
                "timestamp": datetime.now().isoformat()
            }

        return None

    except Exception as e:
        logger.error(f"Error fetching quote for {ticker}: {e}")
        return None


def fetch_kline(ticker: str, period: str = "1mo", count: int = 30) -> Optional[List[Dict]]:
    """
    获取K线数据用于计算技术指标
    """
    try:
        import futu

        host = os.getenv("FUTU_HOST", "127.0.0.1")
        port = int(os.getenv("FUTU_PORT", "11111"))

        quote_ctx = futu.OpenQuoteContext(host=host, port=port)

        ret, data = quote_ctx.get_history_kline(
            ticker,
            start_date="",
            end_date="",
            ktype=futu.KLType.KL_1M if period == "1mo" else futu.KLType.KL_1W,
            fields=futu.KLFields.KL_ALL
        )

        if ret != 0:
            logger.error(f"Failed to get kline for {ticker}: {data}")
            return None

        quote_ctx.close()

        if data is not None:
            return data.to_dict("records")

        return None

    except Exception as e:
        logger.error(f"Error fetching kline for {ticker}: {e}")
        return None


def calculate_market_signals(tickers: List[str], use_fallback: bool = True) -> Dict:
    """
    计算市场相对强弱信号

    返回示例：
    {
        "MU": {
            "latest_price": 640.0,
            "daily_change_pct": 2.1,
            "five_day_change_pct": 8.4,
            "twenty_day_change_pct": 25.2,
            "volume_ratio_20d": 1.8,
            "relative_vs_SOXX_5d": 4.3,
            "relative_vs_SOXX_20d": 12.6,
            "relative_vs_NVDA_5d": 2.0
        }
    }

    如果富途不可用，自动使用 yfinance 作为备用源
    """
    from sources.yfinance_quotes import (
        fetch_yfinance_quote as yf_quote,
        fetch_yfinance_history as yf_history,
        calculate_market_signals_yfinance as yf_signals,
        is_futu_available
    )

    # 先尝试富途
    futu_available = is_futu_available()

    if not futu_available:
        logger.warning("富途 OpenD 不可用，使用 Yahoo Finance 备用源")
        return yf_signals(tickers)

    # 富途可用，正常执行
    signals = {}

    # 获取各股票最新行情
    quotes = {}
    for ticker in tickers:
        quote = fetch_daily_quote(ticker)
        if quote:
            quotes[ticker] = quote

    # 如果富途获取不到，改用 yfinance
    if not quotes and use_fallback:
        logger.warning("富途行情获取失败，使用 Yahoo Finance 备用源")
        return yf_signals(tickers)

    # 获取5日和20日变化
    for ticker in tickers:
        kline_data = fetch_kline(ticker, period="1mo", count=25)

        if kline_data and len(kline_data) >= 20:
            latest = kline_data[-1]
            five_day_ago = kline_data[-6] if len(kline_data) > 5 else kline_data[0]
            twenty_day_ago = kline_data[-21] if len(kline_data) > 20 else kline_data[0]

            latest_price = float(latest.get("close", 0))
            five_day_price = float(five_day_ago.get("close", 0))
            twenty_day_price = float(twenty_day_ago.get("close", 0))

            five_day_change = ((latest_price - five_day_price) / five_day_price * 100) if five_day_price > 0 else 0
            twenty_day_change = ((latest_price - twenty_day_price) / twenty_day_price * 100) if twenty_day_price > 0 else 0

            quote = quotes.get(ticker, {})
            # 计算近5日和近20日平均成交量和平均收盘价
            volumes = [float(k.get("volume", 0)) for k in kline_data]
            closes = [float(k.get("close", 0)) for k in kline_data]
            vol_5d_avg = sum(volumes[-5:]) / min(5, len(volumes)) if len(volumes) >= 5 else (sum(volumes) / len(volumes) if volumes else 0)
            vol_20d_avg = sum(volumes[-20:]) / min(20, len(volumes)) if len(volumes) >= 20 else (sum(volumes) / len(volumes) if volumes else 0)
            price_5d_avg = sum(closes[-5:]) / min(5, len(closes)) if len(closes) >= 5 else (sum(closes) / len(closes) if closes else 0)
            price_20d_avg = sum(closes[-20:]) / min(20, len(closes)) if len(closes) >= 20 else (sum(closes) / len(closes) if closes else 0)

            signals[ticker] = {
                "latest_price": latest_price,
                "daily_change_pct": quote.get("daily_change_pct", 0),
                "five_day_change_pct": round(five_day_change, 2),
                "twenty_day_change_pct": round(twenty_day_change, 2),
                "volume": quote.get("volume", 0),
                "volume_5d_avg": round(vol_5d_avg, 2),
                "volume_20d_avg": round(vol_20d_avg, 2),
                "price_5d_avg": round(price_5d_avg, 2),
                "price_20d_avg": round(price_20d_avg, 2),
            }

            # 计算相对于SOXX的强弱
            if "SOXX" in signals:
                signals[ticker]["relative_vs_SOXX_5d"] = round(
                    signals[ticker]["five_day_change_pct"] - signals["SOXX"]["five_day_change_pct"], 2
                )
                signals[ticker]["relative_vs_SOXX_20d"] = round(
                    signals[ticker]["twenty_day_change_pct"] - signals["SOXX"]["twenty_day_change_pct"], 2
                )

            # 计算相对于NVDA的强弱
            if ticker != "NVDA" and "NVDA" in signals:
                signals[ticker]["relative_vs_NVDA_5d"] = round(
                    signals[ticker]["five_day_change_pct"] - signals["NVDA"]["five_day_change_pct"], 2
                )
        else:
            # 如果K线数据不足，返回最新行情
            quote = quotes.get(ticker, {})
            if quote:
                signals[ticker] = {
                    "latest_price": quote.get("latest_price", 0),
                    "daily_change_pct": quote.get("daily_change_pct", 0),
                    "five_day_change_pct": 0,
                    "twenty_day_change_pct": 0,
                    "volume": quote.get("volume", 0),
                    "volume_5d_avg": 0,
                    "volume_20d_avg": 0,
                    "price_5d_avg": 0,
                    "price_20d_avg": 0,
                }

    return signals


def save_quotes(signals: Dict, date: str):
    """
    保存行情数据到JSON文件
    """
    output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, f"{date}_quotes.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)

    logger.info(f"Quotes saved to {output_path}")
    return output_path