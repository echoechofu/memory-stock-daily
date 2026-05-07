"""
存储价格信号提取器

从抓取到的文章（标题 + 摘要）中提取结构化价格信号
适用于：TrendForce RSS、Google News RSS 等摘要有限的来源
"""
import re
from typing import List, Dict


PRODUCT_PATTERNS = {
    "DRAM": ["dram", "ddr4", "ddr5", "lpddr", "gddr",
             "server dram", "consumer dram", "mobile dram", "specialty dram"],
    "NAND": ["nand", "flash memory", "ssd", "enterprise ssd", "3d nand", "qlc", "tlc"],
    "HBM": ["hbm2", "hbm3", "hbm3e", "hbm4", "high bandwidth memory"],
    "Server": ["server dram", "enterprise ssd", "ai server", "data center", "cloud server"]
}


def _safe_findall(pattern: str, text: str):
    try:
        return re.findall(pattern, text, re.IGNORECASE)
    except re.error:
        return []


def _extract_price_info(text: str):
    """返回 (direction, change_pct, period, sentence)"""
    t = text.lower()

    # ─── 上涨（有百分比）───
    up_pcts = [
        r"(?:prices?|dram|nand|flash)?\s*(?:jump|surge|rising|rise|up\s+to|increase|soar|gain|climb)\s+(?:by\s+)?(?:up\s+to\s+)?(\d+(?:\.\d+)?)\s*%",
        r"(?:dram|nand|flash)\s+(?:up\s+to\s+|up\s+)(\d+(?:\.\d+)?)\s*%",
        r"increase\s+by\s+~\s*(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+(?:in|for|this)\s+(?:q[1-4]|quarter)",
        r"surge\s+(\d+(?:\.\d+)?)\s*%",
        r"(?:price\s+)?surge\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%",
        r"(?:predicted|forecast|expected|seen)?\s*(?:to\s+)?(?:jump|rise|increase|surge|up)\s+(\d+(?:\.\d+)?)\s*%",
    ]
    for pat in up_pcts:
        matches = _safe_findall(pat, t)
        if matches:
            pct = str(matches[0]) if isinstance(matches[0], str) else str(matches[0])
            period = "QoQ"
            if re.search(r"\byoy\b", t): period = "YoY"
            elif re.search(r"\bmom\b", t): period = "MoM"
            m = re.search(rf".{{0,100}}{pat}.{{0,100}}", t)
            sentence = m.group(0) if m else text[:150]
            return "up", pct, period, sentence

    # ─── 上涨（无百分比关键词）───
    up_nopct = [
        r"surge[s]?\s+",
        r"soar[s]?\s+",
        r"prices?\s+(?:surge|soar|jump|rise|spike)",
        r"(?:dram|nand|flash)\s+(?:price\s+)?(?:surge|soar|jump|rise|spike)",
    ]
    for pat in up_nopct:
        if re.search(pat, t):
            m = re.search(rf".{{0,100}}{pat}.{{0,100}}", t)
            sentence = m.group(0) if m else text[:150]
            return "up", "", "unknown", sentence

    # ─── 特定无百分比上涨信号 ───
    special_up = [
        r"sell(?:s|ing|out)\s+(?:out\s+)?(?:all\s+)?(?:their?|its?)?\s*(?:2026|2027|2028|2029)?\s*(?:hbm|supply|inventory|capacity)",
        r"(?:2026|2027|2028|2029)?\s*hbm4?\s+(?:sell|supply|inventory|capacity)\s+(?:out|sold)?",
        r"margins?\s+(?:exceed|surpass|beat)\s+\d+",
        r"record\s+high",
    ]
    for pat in special_up:
        if re.search(pat, t):
            m = re.search(rf".{{0,100}}{pat}.{{0,100}}", t)
            sentence = m.group(0) if m else text[:150]
            return "up", "", "unknown", sentence

    # ─── 下跌 ───
    down_pcts = [
        r"(?:prices?|dram|nand|flash)\s+(?:drop|fall|decline|decrease|plunge|cut)\s+(?:by\s+)?(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s*(?:qoq|quarterly)?\s*(?:drop|fall|decline)",
    ]
    for pat in down_pcts:
        matches = _safe_findall(pat, t)
        if matches:
            pct = str(matches[0]) if isinstance(matches[0], str) else str(matches[0])
            m = re.search(rf".{{0,100}}{pat}.{{0,100}}", t)
            sentence = m.group(0) if m else text[:150]
            return "down", pct, "unknown", sentence

    # ─── 动能放缓 ───
    slow_patterns = [
        r"pace\s+(?:of\s+)?(?:gains?|rises?)\s+(?:is|are)?\s*(?:slow|slown|moderat|easing)",
        r"gains?\s+(?:are|is)\s+(?:slow|slown|moderat|losing\s+steam|easing)",
        r"(?:gains?|rises?)\s+(?:are|is)\s+(?:slow|slown|moderat|easing)",
        r"(?:pace|momentum)\s+(?:of\s+)?(?:price\s+)?(?:gains?)\s+(?:is|are)?\s*(?:slow|slown|easing|moderat)",
    ]
    for pat in slow_patterns:
        if re.search(pat, t):
            m = re.search(rf".{{0,100}}{pat}.{{0,100}}", t)
            sentence = m.group(0) if m else text[:150]
            return "up_but_slowing", "", "unknown", sentence

    return "unknown", "", "unknown", ""


def _classify_product(text: str) -> List[str]:
    t = text.lower()
    products = []
    for product, kws in PRODUCT_PATTERNS.items():
        for kw in kws:
            if re.search(rf"\b{re.escape(kw)}\b", t):
                products.append(product)
                break
    return products


def _supply_signal(text: str) -> str:
    t = text.lower()
    for p in ["shortage", "supply tight", "tight supply", "supply constrain",
              "fab utilization high", "supply short", "constrained supply"]:
        if re.search(rf"\b{re.escape(p)}\b", t): return "tight"
    for p in ["oversupply", "supply loose", "demand weak", "demand soft", "inventory high", "supply abundant"]:
        if re.search(rf"\b{re.escape(p)}\b", t): return "loose"
    return "unknown"


def _hbm_signals(text: str) -> List[str]:
    t = text.lower()
    results = []
    patterns = [
        (r"hbm\s+sold\s+out", "HBM sold out"),
        (r"hbm\s+shortage", "HBM shortage"),
        (r"hbm\s+tight", "HBM tight"),
        (r"hbm\s+supply\s+short", "HBM supply short"),
        (r"hbm\s+(?:ai|gpu)\s+demand", "HBM AI/GPU demand"),
        (r"ai\s+server\s+hbm", "AI server HBM"),
        # 顺序无关的 sold out 信号（文章格式：Sells Out ... HBM4）
        (r"sell(?:s|ing|out)\s+[^.]*?hbm", "HBM sold out"),
    ]
    for pat, label in patterns:
        if re.search(pat, t): results.append(label)
    return list(set(results))


def _demand_signals(text: str) -> List[str]:
    t = text.lower()
    results = []
    patterns = [
        (r"ai\s+server", "AI server"),
        (r"data\s+center", "Data center"),
        (r"cloud\s+(?:capex|demand|server)", "Cloud demand"),
        (r"gpu\s+demand", "GPU demand"),
        (r"ai\s+(?:inference|training)", "AI inference/training"),
        (r"enterprise\s+demand", "Enterprise demand"),
        (r"ai\s+chip\s+demand", "AI chip demand"),
        (r"csp\s+demand", "CSP demand"),
        (r"server\s+demand", "Server demand"),
        (r"smartphone\s+demand", "Smartphone demand"),
        (r"ai\s+demand", "AI demand"),
    ]
    for pat, label in patterns:
        if re.search(pat, t): results.append(label)
    return results


def _capex_signals(text: str) -> List[str]:
    t = text.lower()
    results = []
    patterns = [
        (r"\bcapex\b", "CapEx"),
        (r"capacity\s+expansion", "Capacity expansion"),
        (r"fab\s+construction", "Fab construction"),
        (r"production\s+expansion", "Production expansion"),
        (r"new\s+capacity", "New capacity"),
        (r"capacity\s+increase", "Capacity increase"),
        (r"oversupply\s+risk", "Oversupply risk"),
        (r"capacity\s+shift", "Capacity shift"),
        (r"production\s+shift", "Production shift"),
        (r"capacity\s+allocation", "Capacity allocation"),
    ]
    for pat, label in patterns:
        if re.search(pat, t): results.append(label)
    return results


def _risk_signals(text: str) -> List[str]:
    t = text.lower()
    risks = []
    patterns = [
        (r"pace\s+(?:of\s+)?(?:gains?)\s+(?:is|are)?\s*(?:slow|slown|moderat|easing)", "price momentum slowed"),
        (r"oversupply\s+risk", "oversupply risk"),
        (r"hbm\s+(?:sold\s+out|shortage)", "HBM shortage"),
        (r"demand\s+weak", "demand weakness"),
        (r"supply\s+loose", "supply loose"),
        (r"price\s+(?:is\s+)?(?:peak|top)", "price peak risk"),
    ]
    for pat, label in patterns:
        if re.search(pat, t): risks.append(label)
    return list(set(risks))


def extract_signals_from_article(article: Dict) -> List[Dict]:
    title = article.get("title", "")
    summary = article.get("summary", "")
    raw_text = article.get("raw_text", "")
    text = f"{title} {summary} {raw_text}".strip()
    if not text:
        return []

    products = _classify_product(text)
    if not products:
        return []

    direction, change_pct, period, sentence = _extract_price_info(text)
    supply = _supply_signal(text)
    hbm = _hbm_signals(text)
    demand = _demand_signals(text)
    capex = _capex_signals(text)
    risks = _risk_signals(text)

    if not sentence:
        sentence = title

    metric = "unknown"
    if re.search(r"contract price", text.lower()): metric = "contract price"
    elif re.search(r"spot price", text.lower()): metric = "spot price"
    elif re.search(r"\basp\b", text.lower()): metric = "ASP"

    signals = []
    for product in products:
        sig = {
            "product": product,
            "metric": metric,
            "direction": direction,
            "change_pct": change_pct,
            "period": period,
            "sentence": sentence[:200],
            "supply_signal": supply,
            "hbm_signals": hbm,
            "demand_signals": demand,
            "capex_signals": capex,
            "risk_signals": risks,
            "title": title,
            "url": article.get("url", ""),
            "published_at": article.get("published_at", ""),
            "source": article.get("source", ""),
        }
        signals.append(sig)
    return signals


def extract_signals_from_articles(articles: List[Dict]) -> Dict:
    all_signals = []
    for article in articles:
        all_signals.extend(extract_signals_from_article(article))

    result = {
        cat: {"status": "unknown", "evidence": [], "signals": []}
        for cat in ["dram", "nand", "hbm", "capex", "downstream", "earnings_revision"]
    }
    result["all_signals"] = all_signals

    product_map = {"DRAM": "dram", "NAND": "nand", "HBM": "hbm", "Server": "downstream"}
    priority = {"up": 4, "up_but_slowing": 3, "neutral": 2, "down": 1, "unknown": 0}
    seen_evidence_urls = {cat: set() for cat in result}  # 每个 category 按 URL 去重

    for sig in all_signals:
        key = product_map.get(sig["product"])
        if not key:
            continue
        cur = result[key]["status"]
        new = sig["direction"]
        if priority.get(new, 0) > priority.get(cur, 0):
            result[key]["status"] = new
        if sig["change_pct"] != "unknown" or sig["sentence"]:
            ev = {
                "title": sig["title"],
                "url": sig["url"],
                "published_at": sig["published_at"],
                "direction": sig["direction"],
                "change_pct": sig.get("change_pct", "unknown"),
                "period": sig.get("period", "unknown"),
                "sentence": sig["sentence"],
                "supply_signal": sig.get("supply_signal", "unknown"),
                "risk_signals": sig.get("risk_signals", []),
                "hbm_signals": sig.get("hbm_signals", []),
                "demand_signals": sig.get("demand_signals", []),
            }
            if sig["url"] not in seen_evidence_urls[key]:
                seen_evidence_urls[key].add(sig["url"])
                result[key]["evidence"].append(ev)
        result[key]["signals"].append(sig)

    for sig in all_signals:
        if sig.get("supply_signal") in ["tight", "loose"]:
            ev = {
                "title": sig["title"], "url": sig["url"],
                "supply_signal": sig["supply_signal"], "sentence": sig["sentence"],
                "direction": sig["direction"],
                "change_pct": sig.get("change_pct", "unknown"),
                "period": sig.get("period", "unknown"),
                "risk_signals": [],
            }
            if ev["url"] not in {e["url"] for e in result["capex"]["evidence"]}:
                result["capex"]["evidence"].append(ev)
                if result["capex"]["status"] == "unknown":
                    result["capex"]["status"] = sig["supply_signal"]
        if sig.get("demand_signals"):
            ev = {
                "title": sig["title"], "url": sig["url"],
                "demand": sig["demand_signals"], "sentence": sig["sentence"],
                "direction": sig["direction"],
                "change_pct": sig.get("change_pct", "unknown"),
                "period": sig.get("period", "unknown"),
                "risk_signals": [],
            }
            if ev["url"] not in {e["url"] for e in result["downstream"]["evidence"]}:
                result["downstream"]["evidence"].append(ev)
                if result["downstream"]["status"] == "unknown":
                    result["downstream"]["status"] = "ai_driven"

    return result
