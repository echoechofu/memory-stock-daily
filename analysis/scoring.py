"""
信号打分系统
每天输出 0-5 分
"""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def calculate_score(market_signals: Dict, extracted_signals: Dict) -> Dict:
    """
    计算综合评分

    五个分项：
    1. 行情相对强弱：0/1
    2. DRAM/NAND 价格信号：0/1
    3. HBM 供需信号：0/1
    4. 同行/竞争对手验证：0/1
    5. 下游需求验证：0/1
    """
    scores = {
        "market_strength": 0,
        "dram_nand_price": 0,
        "hbm_supply": 0,
        "competitor_verification": 0,
        "downstream_demand": 0
    }

    reasons = {
        "market_strength": "",
        "dram_nand_price": "",
        "hbm_supply": "",
        "competitor_verification": "",
        "downstream_demand": ""
    }

    # 1. 行情相对强弱
    mu_signals = market_signals.get("MU", {})
    soxx_signals = market_signals.get("SOXX", {})

    mu_5d = mu_signals.get("five_day_change_pct", 0)
    mu_20d = mu_signals.get("twenty_day_change_pct", 0)
    soxx_5d = soxx_signals.get("five_day_change_pct", 0)
    soxx_20d = soxx_signals.get("twenty_day_change_pct", 0)

    if mu_5d > soxx_5d or mu_20d > soxx_20d:
        scores["market_strength"] = 1
        reasons["market_strength"] = f"MU 5日涨幅 {mu_5d}% vs SOXX {soxx_5d}%，MU 强于基准"
    else:
        reasons["market_strength"] = f"MU 未跑赢 SOXX（MU 5日 {mu_5d}% vs SOXX {soxx_5d}%）"

    # 2. DRAM/NAND 价格信号
    dram_status = extracted_signals.get("dram", {}).get("status", "unknown")
    nand_status = extracted_signals.get("nand", {}).get("status", "unknown")
    dram_has_number = any(
        ev.get("change_pct") not in ("unknown", "")
        for ev in extracted_signals.get("dram", {}).get("evidence", [])
    )
    nand_has_number = any(
        ev.get("change_pct") not in ("unknown", "")
        for ev in extracted_signals.get("nand", {}).get("evidence", [])
    )

    if dram_status in ("up", "up_but_slowing") or nand_status in ("up", "up_but_slowing"):
        scores["dram_nand_price"] = 1
        dram_num = " (有数字)" if dram_has_number else ""
        nand_num = " (有数字)" if nand_has_number else ""
        reasons["dram_nand_price"] = f"DRAM: {dram_status}{dram_num}, NAND: {nand_status}{nand_num}，价格信号正向"
    else:
        reasons["dram_nand_price"] = f"未观察到 DRAM/NAND 价格信号（DRAM: {dram_status}, NAND: {nand_status}）"

    # 3. HBM 供需信号
    hbm_evidence = extracted_signals.get("hbm", {}).get("evidence", [])
    has_hbm_signal = any(
        ev.get("hbm_signals") or ev.get("supply_signal") in ("tight",)
        for ev in hbm_evidence
    )

    if has_hbm_signal:
        scores["hbm_supply"] = 1
        reasons["hbm_supply"] = "观察到 HBM 供应紧张信号"
    else:
        reasons["hbm_supply"] = "未观察到明确的 HBM 供需紧张信号"

    # 4. 同行/竞争对手验证
    competitors = ["Samsung", "SK hynix", "Micron", "SanDisk", "Western Digital"]
    competitor_evidence = []

    for category in ["dram", "nand", "hbm"]:
        for ev in extracted_signals.get(category, {}).get("evidence", []):
            title = ev.get("title", "").lower()
            for comp in competitors:
                if comp.lower() in title:
                    competitor_evidence.append(comp)

    if competitor_evidence:
        scores["competitor_verification"] = 1
        reasons["competitor_verification"] = f"观察到竞争对手信号：{set(competitor_evidence)}"
    else:
        reasons["competitor_verification"] = "未观察到竞争对手验证信号"

    # 5. 下游需求验证
    downstream_status = extracted_signals.get("downstream", {}).get("status", "unknown")
    downstream_evidence = extracted_signals.get("downstream", {}).get("evidence", [])
    has_demand_signals = any(
        ev.get("demand_signals") or ev.get("demand")
        for ev in downstream_evidence
    )

    if downstream_status in ("up", "ai_driven") and has_demand_signals:
        scores["downstream_demand"] = 1
        reasons["downstream_demand"] = "观察到 AI server 下游需求信号"
    else:
        reasons["downstream_demand"] = f"未观察到明确的下游需求验证（downstream status: {downstream_status}）"

    # 总分
    total_score = sum(scores.values())

    # 状态描述
    if total_score >= 4:
        status = "强正向"
    elif total_score >= 3:
        status = "温和正向"
    elif total_score >= 2:
        status = "中性"
    elif total_score >= 1:
        status = "温和负向"
    else:
        status = "强负向"

    return {
        "total_score": total_score,
        "max_score": 5,
        "status": status,
        "scores": scores,
        "reasons": reasons
    }


def extract_risk_signals(news_articles: List[Dict], signals: Dict = None) -> List[Dict]:
    """
    提取风险信号
    优先从 signals（新，正则路径）读取，其次从 news_articles 兜底
    """
    risks = []

    # 从 signals（新路径）提取
    if signals:
        for cat in ["dram", "nand", "hbm", "capex", "downstream"]:
            for ev in signals.get(cat, {}).get("evidence", []):
                for risk_label in ev.get("risk_signals", []):
                    risks.append({
                        "type": _classify_risk_type(risk_label),
                        "level": "medium",
                        "evidence": ev.get("title", ""),
                        "url": ev.get("url", ""),
                        "published_at": ev.get("published_at", "")
                    })

        # 从 all_signals 兜底（同一篇文章可能多个 product）
        seen = {(r["evidence"], r["type"]) for r in risks}
        for sig in signals.get("all_signals", []):
            for risk_label in sig.get("risk_signals", []):
                risk_type = _classify_risk_type(risk_label)
                title = sig.get("title", "")
                if (title, risk_type) not in seen:
                    seen.add((title, risk_type))
                    risks.append({
                        "type": risk_type,
                        "level": "medium",
                        "evidence": title,
                        "url": sig.get("url", ""),
                        "published_at": sig.get("published_at", "")
                    })

    # 兜底：从 news_articles 关键词匹配（万一正则路径漏抓）
    risk_keywords = {
        "price_slowdown": ["price growth slows", "price decline", "contract price flat", "spot price weakness"],
        "hbm_competition": ["Samsung HBM qualification", "HBM price pressure", "HBM oversupply"],
        "capex_overheat": ["aggressive CapEx", "capacity expansion", "new fab", "oversupply risk"],
        "earnings_risk": ["EPS estimate cut", "guidance cut", "gross margin pressure"]
    }

    existing_titles = {r["evidence"] for r in risks}
    for article in news_articles:
        text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
        title = article.get("title", "")

        for risk_type, keywords in risk_keywords.items():
            for kw in keywords:
                if kw.lower() in text:
                    if title not in existing_titles:
                        risks.append({
                            "type": risk_type,
                            "level": "medium",
                            "evidence": title,
                            "url": article.get("url", ""),
                            "published_at": article.get("published_at", "")
                        })
                        existing_titles.add(title)
                    break

    return risks


def _classify_risk_type(label: str) -> str:
    """将 risk_signals 标签映射到标准风险类型"""
    label_lower = label.lower()
    if "slow" in label_lower or "momentum slowed" in label_lower or "easing" in label_lower:
        return "price_slowdown"
    if "oversupply" in label_lower:
        return "capex_overheat"
    if "hbm shortage" in label_lower or "sold out" in label_lower:
        return "hbm_competition"
    if "demand weak" in label_lower or "demand soft" in label_lower:
        return "price_slowdown"
    if "supply loose" in label_lower:
        return "capex_overheat"
    if "peak" in label_lower or "top" in label_lower:
        return "price_slowdown"
    return "price_slowdown"


def format_score_report(score_result: Dict, risk_signals: List[Dict]) -> str:
    """
    格式化评分报告
    """
    lines = []
    lines.append(f"评分：{score_result['total_score']}/5")
    lines.append(f"状态：{score_result['status']}")
    lines.append("")

    lines.append("【评分拆解】")
    for key, value in score_result["scores"].items():
        reason = score_result["reasons"][key]
        lines.append(f"- {key}: {value}/1 — {reason}")

    if risk_signals:
        lines.append("")
        lines.append("【风险信号】")
        for risk in risk_signals:
            lines.append(f"- {risk['type']} ({risk['level']}): {risk['evidence']}")

    return "\n".join(lines)