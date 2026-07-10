# -*- coding: utf-8 -*-
"""用户可见回复的输出契约模块。

本包集中处理世界书里对“用户能看到的回复格式”的要求，包括契约识别、
prompt 提示、尾部模板续写、校验和诊断压缩。
"""

from app.services.output_contracts.diagnostics import diagnostics_to_dict
from app.services.output_contracts.detector import (
    annotate_entries,
    detect_entry_heuristic,
    detect_entry_llm,
    detect_single_entry,
)
from app.services.output_contracts.extractor import build_visible_output_contract
from app.services.output_contracts.prompt import build_output_contract_prompt
from app.services.output_contracts.tail import (
    build_tail_template_directive,
    build_template_scaffold,
    continue_missing_tail_blocks,
    find_missing_tail_blocks,
)
from app.services.output_contracts.types import (
    ContractDiagnostics,
    ContractSource,
    ForbiddenTermRule,
    OutputContractMode,
    SectionContract,
    TailBlockContract,
    VisibleOutputContract,
)
from app.services.output_contracts.validator import validate_visible_output

__all__ = [
    "build_output_contract_prompt",
    "build_tail_template_directive",
    "build_template_scaffold",
    "build_visible_output_contract",
    "ContractDiagnostics",
    "ContractSource",
    "continue_missing_tail_blocks",
    "annotate_entries",
    "detect_entry_heuristic",
    "detect_entry_llm",
    "detect_single_entry",
    "diagnostics_to_dict",
    "find_missing_tail_blocks",
    "ForbiddenTermRule",
    "OutputContractMode",
    "SectionContract",
    "TailBlockContract",
    "validate_visible_output",
    "VisibleOutputContract",
]
