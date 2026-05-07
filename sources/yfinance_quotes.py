"""
Yahoo Finance 行情模块 - 作为富途的备用源
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def fetch_yfinance_quote(ticker: str) -> Optional[Dict]:
    """
    获取单个股票的最新行情（Yahoo Finance）
    """
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        info = stock.info

        return {
            "ticker": ticker,
            "latest_price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
            "daily_change_pct": info.get("regularMarketChangePercent", 0),
            "volume": info.get("regularMarketVolume", 0),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.warning(f"yfinance failed for {ticker}: {e}")
        return None


def fetch_yfinance_history(ticker: str, period: str = "1mo") -> Optional[List[Dict]]:
    """
    获取历史数据用于计算技术指标
    period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
    """
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)

        if hist is None or hist.empty:
            return None

        records = []
        for date, row in hist.iterrows():
            records.append({
                "date": date.isoformat(),
                "open": row["Open"],
                "high": row["High"],
                "low": row["Low"],
                "close": row["Close"],
                "volume": row["Volume"]
            })

        return records

    except Exception as e:
        logger.warning(f"yfinance history failed for {ticker}: {e}")
        return None


def calculate_market_signals_yfinance(tickers: List[str]) -> Dict:
    """
    使用 Yahoo Finance 计算市场相对强弱信号
    """
    signals = {}

    # 获取各股票最新行情
    quotes = {}
    for ticker in tickers:
        quote = fetch_yfinance_quote(ticker)
        if quote:
            quotes[ticker] = quote
            logger.info(f"yfinance quote {ticker}: ${quote['latest_price']:.2f} ({quote['daily_change_pct']:+.2f}%)")

    # 获取历史数据计算5日和20日变化
    for ticker in tickers:
        hist_data = fetch_yfinance_history(ticker, period="2mo")

        if hist_data and len(hist_data) >= 25:
            latest = hist_data[-1]
            five_day_ago = hist_data[-6] if len(hist_data) > 5 else hist_data[0]
            twenty_day_ago = hist_data[-21] if len(hist_data) > 20 else hist_data[0]

            latest_price = float(latest.get("close", 0))
            five_day_price = float(five_day_ago.get("close", 0))
            twenty_day_price = float(twenty_day_ago.get("close", 0))

            five_day_change = ((latest_price - five_day_price) / five_day_price * 100) if five_day_price > 0 else 0
            twenty_day_change = ((latest_price - twenty_day_price) / twenty_day_price * 100) if twenty_day_price > 0 else 0

            quote = quotes.get(ticker, {})
            volumes = [float(h.get("volume", 0)) for h in hist_data]
            closes = [float(h.get("close", 0)) for h in hist_data]
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
            # 数据不足时返回最新行情
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

    logger.info(f"yfinance market signals: {list(signals.keys())}")
    return signals


def is_futu_available() -> bool:
    """
    检查富途 OpenD 是否可用
    """
    try:
        import futu

        host = os.getenv("FUTU_HOST", "127.0.0.1")
        port = int(os.getenv("FUTU_PORT", "11111"))

        quote_ctx = futu.OpenQuoteContext(host=host, port=port)
        ret, data = quote_ctx.get_stock_quote(["MU"])
        quote_ctx.close()

        if ret == 0:
            return True
        else:
            logger.warning(f"Futu API returned error: {data}")
            return False

    except Exception as e:
        logger.warning(f"Futu not available: {e}")
        return False