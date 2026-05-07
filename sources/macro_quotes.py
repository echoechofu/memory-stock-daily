"""
宏观数据抓取模块 - 黄金 / WTI 原油 / 美元指数
通过 yfinance 获取现价、涨跌幅、5日/20日均量
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# yfinance ticker 映射
MACRO_TICKERS = {
    "gold":  "GLD",   # SPDR Gold Shares (黄金 ETF)
    "oil":   "USO",   # United States Oil Fund (WTI 原油)
    "usd":   "UUP",   # ProShares UltraStrengthUSD (美元指数)
}

# 显示名称
MACRO_NAMES = {
    "gold": "黄金 (GLD)",
    "oil":  "WTI原油 (USO)",
    "usd":  "美元指数 (UUP)",
}


def fetch_macro_price(ticker: str) -> Optional[Dict]:
    """
    获取单个宏观品种的最新行情（Yahoo Finance）
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
        logger.warning(f"yfinance macro failed for {ticker}: {e}")
        return None


def fetch_macro_history(ticker: str, period: str = "2mo") -> Optional[List[Dict]]:
    """
    获取历史数据用于计算技术指标
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
                "open":  row["Open"],
                "high":  row["High"],
                "low":   row["Low"],
                "close": row["Close"],
                "volume": row["Volume"]
            })

        return records

    except Exception as e:
        logger.warning(f"yfinance macro history failed for {ticker}: {e}")
        return None


def calculate_macro_signals() -> Dict:
    """
    计算宏观品种市场信号（现价、涨跌幅、5日/20日变化、均量）

    返回示例：
    {
        "gold": {
            "latest_price": 185.42,
            "daily_change_pct": -0.53,
            "five_day_change_pct": -1.23,
            "twenty_day_change_pct": 2.10,
            "volume": 12345678,
            "volume_5d_avg": 14000000,
            "volume_20d_avg": 13500000,
        },
        ...
    }
    """
    signals = {}

    # 获取各品种最新行情
    quotes = {}
    for name, ticker in MACRO_TICKERS.items():
        quote = fetch_macro_price(ticker)
        if quote:
            quotes[name] = quote
            logger.info(f"Macro {name}: ${quote['latest_price']:.2f} ({quote['daily_change_pct']:+.2f}%)")

    # 获取历史数据计算 5 日和 20 日变化
    for name, ticker in MACRO_TICKERS.items():
        hist_data = fetch_macro_history(ticker, period="2mo")

        if hist_data and len(hist_data) >= 20:
            latest = hist_data[-1]
            five_day_ago = hist_data[-6] if len(hist_data) > 5 else hist_data[0]
            twenty_day_ago = hist_data[-21] if len(hist_data) > 20 else hist_data[0]

            latest_price = float(latest.get("close", 0))
            five_day_price = float(five_day_ago.get("close", 0))
            twenty_day_price = float(twenty_day_ago.get("close", 0))

            five_day_change = ((latest_price - five_day_price) / five_day_price * 100) if five_day_price > 0 else 0
            twenty_day_change = ((latest_price - twenty_day_price) / twenty_day_price * 100) if twenty_day_price > 0 else 0

            quote = quotes.get(name, {})
            volumes = [float(h.get("volume", 0)) for h in hist_data]
            vol_5d_avg = sum(volumes[-5:]) / min(5, len(volumes)) if len(volumes) >= 5 else (sum(volumes) / len(volumes) if volumes else 0)
            vol_20d_avg = sum(volumes[-20:]) / min(20, len(volumes)) if len(volumes) >= 20 else (sum(volumes) / len(volumes) if volumes else 0)

            signals[name] = {
                "latest_price": round(latest_price, 2),
                "daily_change_pct": round(quote.get("daily_change_pct", 0), 2),
                "five_day_change_pct": round(five_day_change, 2),
                "twenty_day_change_pct": round(twenty_day_change, 2),
                "volume": quote.get("volume", 0),
                "volume_5d_avg": round(vol_5d_avg, 2),
                "volume_20d_avg": round(vol_20d_avg, 2),
                "display_name": MACRO_NAMES.get(name, name),
            }
        else:
            # 数据不足时返回最新行情
            quote = quotes.get(name, {})
            if quote:
                signals[name] = {
                    "latest_price": quote.get("latest_price", 0),
                    "daily_change_pct": round(quote.get("daily_change_pct", 0), 2),
                    "five_day_change_pct": 0,
                    "twenty_day_change_pct": 0,
                    "volume": quote.get("volume", 0),
                    "volume_5d_avg": 0,
                    "volume_20d_avg": 0,
                    "display_name": MACRO_NAMES.get(name, name),
                }

    logger.info(f"Macro signals: {list(signals.keys())}")
    return signals