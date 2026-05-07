"""
MiniMax API 客户端 - 生成存储股日报
"""
import os
import json
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 从环境变量读取配置，不要硬编码任何 key
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-Text-01")


def generate_daily_report(input_data: Dict, prompt_template: str) -> Optional[str]:
    """
    调用 MiniMax API 生成中文日报

    参数：
    - input_data: 包含行情数据、新闻、信号评分的字典
    - prompt_template: Prompt 模板路径

    返回：
    - 生成的中文日报文本，失败返回 None
    """
    if not MINIMAX_API_KEY:
        logger.error("MINIMAX_API_KEY 环境变量未设置")
        return None

    try:
        import openai

        # 设置 MiniMax API
        client = openai.OpenAI(
            api_key=MINIMAX_API_KEY,
            base_url=MINIMAX_BASE_URL
        )

        # 读取 prompt 模板
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..", "prompts", "daily_memory_report.md"
        )

        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                system_prompt = f.read()
        else:
            system_prompt = "你是一个谨慎的半导体存储产业链分析助手。"

        # 构造用户消息
        user_message = f"请根据以下数据生成存储股日报：\n\n{json.dumps(input_data, ensure_ascii=False, indent=2)}"

        # 调用 API
        response = client.chat.completions.create(
            model=MINIMAX_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,  # 较低温度保持准确性
            max_tokens=4000
        )

        report = response.choices[0].message.content
        logger.info("MiniMax API 调用成功")
        return report

    except Exception as e:
        logger.error(f"MiniMax API 调用失败: {e}")
        return None


def generate_report_with_fallback(input_data: Dict, prompt_template: str) -> Dict:
    """
    生成日报，失败时返回原始数据和错误信息
    """
    report = generate_daily_report(input_data, prompt_template)

    result = {
        "success": report is not None,
        "report": report,
        "raw_data": input_data,
        "error": None if report else "MiniMax API 调用失败"
    }

    if not report:
        result["fallback_message"] = (
            "MiniMax API 调用失败，请查看 data/raw 和 data/processed 目录下的原始数据。"
        )

    return result


def save_report(report: str, date: str) -> str:
    """
    保存日报到 reports 目录
    """
    reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(reports_dir, exist_ok=True)

    output_path = os.path.join(reports_dir, f"{date}.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"日报已保存到 {output_path}")
    return output_path