# -*- coding: utf-8 -*-
"""把可见输出契约诊断压缩成 SSE 友好的稳定结构。"""
from __future__ import annotations

from typing import Any

from app.services.output_contracts.types import ContractDiagnostics


def diagnostics_to_dict(diag: ContractDiagnostics) -> dict[str, Any]:
    """把诊断 dataclass 转成前端可依赖的普通 dict。"""
    data: dict[str, Any] = {
        "mode": diag.mode,
        "ok": bool(diag.ok),
        "required": int(diag.required or 0),
        "missing": list(diag.missing or []),
        "invalid_order": list(diag.invalid_order or []),
        "forbidden_hits": list(diag.forbidden_hits or []),
        "repaired": bool(diag.repaired),
        "repair_mode": diag.repair_mode,
    }
    if diag.warnings:
        data["warnings"] = list(diag.warnings)
    return data
