# -*- coding: utf-8 -*-
"""用户可见回复的输出契约模块。

本包集中处理世界书里对“用户能看到的回复格式”的要求，包括契约识别、
prompt 提示、尾部模板续写、校验和诊断压缩。
"""

from app.services.output_contracts.diagnostics import (
    build_contract_sse,
    diagnostics_to_dict,
    split_rules,
)
from app.services.output_contracts.detector import (
    annotate_entries,
    detect_entry_heuristic,
    detect_entry_llm,
    detect_single_entry,
)
from app.services.output_contracts.compiler import compile_contract
from app.services.output_contracts.executor import (
    EnforcementResult,
    enforce_visible_output_contract,
)
from app.services.output_contracts.extractor import build_visible_output_contract
from app.services.output_contracts.policy import resolve_policy
from app.services.output_contracts.prompt import build_output_contract_prompt
from app.services.output_contracts.reconstructor import reconstruct
from app.services.output_contracts.renderer import (
    render_choice_set,
    render_details,
    render_heading,
    render_section,
)
from app.services.output_contracts.rewrite import rewrite_document
from app.services.output_contracts.slotfill import (
    apply_slots,
    fillable_sections,
    request_slots,
)
from app.services.output_contracts.strict import (
    STRICT_STAGES,
    StrictResult,
    render_document,
    run_strict,
    strict_available,
)
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
    SectionKind,
    SpanStrategy,
    TailBlockContract,
    VisibleOutputContract,
)
from app.services.output_contracts.validator import validate_visible_output

__all__ = [
    "build_output_contract_prompt",
    "build_tail_template_directive",
    "build_template_scaffold",
    "build_visible_output_contract",
    "compile_contract",
    "ContractDiagnostics",
    "ContractSource",
    "continue_missing_tail_blocks",
    "annotate_entries",
    "build_contract_sse",
    "split_rules",
    "detect_entry_heuristic",
    "detect_entry_llm",
    "detect_single_entry",
    "diagnostics_to_dict",
    "enforce_visible_output_contract",
    "EnforcementResult",
    "find_missing_tail_blocks",
    "reconstruct",
    "resolve_policy",
    "render_choice_set",
    "render_details",
    "render_heading",
    "render_section",
    "rewrite_document",
    "apply_slots",
    "fillable_sections",
    "request_slots",
    "STRICT_STAGES",
    "StrictResult",
    "render_document",
    "run_strict",
    "strict_available",
    "ForbiddenTermRule",
    "OutputContractMode",
    "SectionContract",
    "SectionKind",
    "SpanStrategy",
    "TailBlockContract",
    "validate_visible_output",
    "VisibleOutputContract",
]
