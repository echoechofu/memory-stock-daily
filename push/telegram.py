"""
Telegram 推送模块

支持双账号推送，从环境变量读取:
- TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID: 账号1
- TELEGRAM_BOT_TOKEN_2 / TELEGRAM_CHAT_ID_2: 账号2（可选）
"""
import os
import logging
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)


def _get_all_bots() -> List[Tuple[str, str]]:
    """返回所有 (bot_token, chat_id) 组合"""
    bots = []
    token1 = os.getenv("TELEGRAM_BOT_TOKEN")
    chat1 = os.getenv("TELEGRAM_CHAT_ID")
    if token1 and chat1:
        bots.append((token1, chat1))

    token2 = os.getenv("TELEGRAM_BOT_TOKEN_2")
    chat2 = os.getenv("TELEGRAM_CHAT_ID_2")
    if token2 and chat2:
        bots.append((token2, chat2))
    return bots


def _clean_markdown(text: str) -> str:
    """
    清理 Markdown 特殊字符，避免 Telegram 解析失败
    - 移除表格语法（| 符）
    - 移除 ** 加粗（改为普通文字）
    - 移除 ## 标题标记
    - 移除 > 引用标记
    - 保留换行和基本文字
    """
    import re

    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        # 跳过纯 Markdown 表格分隔行（如 |---|---|）
        if re.match(r"^\s*\|[\s\-\|]+\|\s*$", line):
            continue
        # 移除表格 leading/trailing | 并替换为分隔符
        if "|" in line and line.strip().startswith("|"):
            line = re.sub(r"^\s*\|\s*", "", line)
            line = re.sub(r"\s*\|\s*$", "", line)
            line = "  " + re.sub(r"\s*\|\s*", " | ", line)
        # 移除加粗语法
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        # 移除标题标记
        line = re.sub(r"^#{1,6}\s*", "", line)
        # 移除引用标记
        line = re.sub(r"^>\s*", "", line)
        # 移除行内代码标记（保留文字）
        line = re.sub(r"`(.*?)`", r"\1", line)
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def _send_single(text: str, bot_token: str, chat_id: str) -> bool:
    """发送给单个 Telegram 账号"""
    import requests

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # 清理 Markdown 语法
    text = _clean_markdown(text)

    # 单条消息最大 3500 字符
    max_length = 3500
    messages = []
    if len(text) > max_length:
        lines = text.split("\n")
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > max_length:
                if current:
                    messages.append(current)
                current = line
            else:
                current += "\n" + line if current else line
        if current:
            messages.append(current)
    else:
        messages.append(text)

    success = True
    for msg in messages:
        try:
            response = requests.post(url, json={
                "chat_id": chat_id,
                "text": msg,
                "disable_web_page_preview": True
            }, timeout=30)
            if response.status_code != 200:
                logger.error(f"Telegram 推送失败（{chat_id}）: {response.text}")
                success = False
        except Exception as e:
            logger.error(f"Telegram 推送异常（{chat_id}）: {e}")
            success = False
    return success


def send_telegram_message(text: str) -> bool:
    """
    发送 Telegram 消息（支持多账号）

    - 读取所有配置的 bot/chat 组合并逐一发送
    - 任一账号失败不影响其他账号
    - 全部失败才返回 False
    """
    bots = _get_all_bots()
    if not bots:
        logger.warning("Telegram 配置未完成，跳过推送")
        return False

    results = [_send_single(text, token, chat) for token, chat in bots]
    return all(results)


def send_telegram_with_retry(text: str, max_retries: int = 3) -> bool:
    """
    带重试的发送
    """
    import time

    for attempt in range(max_retries):
        if send_telegram_message(text):
            return True

        if attempt < max_retries - 1:
            logger.info(f"Telegram 推送失败，{attempt + 1} 秒后重试...")
            time.sleep(attempt + 1)

    logger.error("Telegram 推送最终失败（本地报告已保存）")
    return False


def notify_error(error_message: str) -> bool:
    """
    发送错误通知
    """
    return send_telegram_message(f"⚠️ 存储股日报系统错误\n\n{error_message}")