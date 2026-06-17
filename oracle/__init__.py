"""
擎天·Oracle — DeepSeek API 封装层
翻译 / 提取 / PI 生成
"""

from .client import deepseek_chat, translate, extract_inquiry, generate_pi

__all__ = ["deepseek_chat", "translate", "extract_inquiry", "generate_pi"]
