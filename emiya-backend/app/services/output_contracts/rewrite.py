# -*- coding: utf-8 -*-
"""整篇 rewrite 兜底（ADR-1e §6）。

只有区块严重交织无法无损定位、精确禁词已嵌入正文、或用户显式授权时才允许整篇
rewrite。每轮最多一次、低温执行；失败或仍不合格由调用方保留 rewrite 前最佳版本。
默认配置不静默开启（由 policy.allow_full_rewrite 控制，见 ADR-1f）。
"""
from __future__ import annotations

import logging

from app.services.llm_service import call_deepseek_non_stream
from app.services.output_contracts.prompt import build_output_contract_prompt
from app.services.output_contracts.types import VisibleOutputContract

logger = logging.getLogger(__name__)


async def rewrite_document(
    reply: str,
    contract: VisibleOutputContract,
    *,
    temperature: float = 0.3,
    max_tokens: int = 2400,
) -> str:
    """按契约结构整篇重写回复，保持剧情事实不变。失败返回空串。"""
    directive = build_output_contract_prompt(contract)
    if not directive:
        return ""
    prompt = (
        "请在**不改变剧情事实、人物与语义**的前提下，把下面这段回复重排成满足结构"
        "契约的完整回复。只调整结构、补全缺失区块、修正顺序与标签，不要新增剧情、"
        "不要删改已有正文含义，也不要输出任何解释。\n\n"
        f"{directive}\n\n"
        "原回复：\n"
        f"{reply}"
    )
    try:
        out = await call_deepseek_non_stream(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 — rewrite 失败保留原文
        logger.warning("[输出契约] 整篇 rewrite 调用失败：%s", exc)
        return ""
    return (out or "").strip()
