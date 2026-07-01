# -*- coding: utf-8 -*-
"""世界书注入器：按 position 把激活集分发到 Prompt 各位置。

参见：
  docs/adr/0003-position-fidelity-and-bundled-an-outlet.md
  scanner.py 产出的 ActiveEntry 是这里的输入。

锚点协议：
  在 PromptRenderer 渲染阶段，关键块上会被打上锚点字典：
    {"role": "system", "content": "...", "_anchor": "char_desc" | "mes_example" | "author_note"}
  注入器扫描 messages，找到 _anchor 后在其前/后插入对应 position 的条目，
  并最终剥掉 _anchor 标记字段。
"""
import logging

from app.services.ejs_engine import EJSEngine
from app.services.macro_engine import MacroEngine
from app.services.worldbook.scanner import ActiveEntry
from app.models.worldbook import (
    WI_POSITION_AFTER_CHAR,
    WI_POSITION_AN_BOTTOM,
    WI_POSITION_AN_TOP,
    WI_POSITION_AT_DEPTH,
    WI_POSITION_BEFORE_CHAR,
    WI_POSITION_EM_BOTTOM,
    WI_POSITION_EM_TOP,
    WI_POSITION_OUTLET,
)

logger = logging.getLogger(__name__)

# ─── 锚点常量 ───
ANCHOR_CHAR_DESC = "char_desc"
ANCHOR_MES_EXAMPLE = "mes_example"
ANCHOR_AUTHOR_NOTE = "author_note"
ANCHOR_KEY = "_anchor"

# position → 锚点 + (before | after) 映射
_POSITION_ANCHOR = {
    WI_POSITION_BEFORE_CHAR: (ANCHOR_CHAR_DESC, "before"),
    WI_POSITION_AFTER_CHAR: (ANCHOR_CHAR_DESC, "after"),
    WI_POSITION_AN_TOP: (ANCHOR_AUTHOR_NOTE, "before"),
    WI_POSITION_AN_BOTTOM: (ANCHOR_AUTHOR_NOTE, "after"),
    WI_POSITION_EM_TOP: (ANCHOR_MES_EXAMPLE, "before"),
    WI_POSITION_EM_BOTTOM: (ANCHOR_MES_EXAMPLE, "after"),
}


class WorldbookInjector:
    """注入器：把激活的 ActiveEntry 分发到 messages 的 8 个位置。

    OUTLET 位置由 PromptRenderer 在渲染阶段直接消费（见 prompt_renderer.py），
    不在这里处理。本类只处理：BEFORE_CHAR / AFTER_CHAR / AN_TOP/BOTTOM /
    EM_TOP/BOTTOM / AT_DEPTH。
    """

    @staticmethod
    def inject(
        messages: list[dict],
        activated: list[ActiveEntry],
        history_start_idx: int,
        scope: dict | None = None,
    ) -> list[dict]:
        """
        Args:
            messages: 已渲染好的完整消息列表（含 system 区 + history）
            activated: 扫描器产出的激活集（已按 order 排序）
            history_start_idx: history 区在 messages 中的起始下标
                （即第一条 user/assistant 消息的位置）
            scope: MacroEngine 变量作用域，详见 docs/adr/0007

        Returns:
            新的 messages 列表（不修改原列表）。所有锚点标记字段已剥掉。
        """
        if not activated:
            return WorldbookInjector._strip_anchors(messages)

        # EJS 先跑（MVU 兼容，详见 ADR-0010），再跑 MacroEngine
        rendered_entries: list[ActiveEntry] = []
        for ae in activated:
            ejs_scope = dict((scope or {}).get("local") or {})
            if ae.entry_lookup:
                ejs_scope["__wi_entries"] = ae.entry_lookup
            c = EJSEngine.render(ae.content, ejs_scope)
            c = MacroEngine.render(c, scope)
            rendered_entries.append(
                ActiveEntry(
                    entry=ae.entry,
                    worldbook_id=ae.worldbook_id,
                    worldbook_name=ae.worldbook_name,
                    position=ae.position,
                    depth=ae.depth,
                    order=ae.order,
                    role=ae.role,
                    outlet_name=ae.outlet_name,
                    content=c,
                    entry_lookup=ae.entry_lookup,
                )
            )
        activated = rendered_entries

        # 按 position 分桶
        buckets: dict[int, list[ActiveEntry]] = {}
        for ae in activated:
            buckets.setdefault(ae.position, []).append(ae)

        result = list(messages)
        new_history_start = history_start_idx

        # ── 锚点驱动的位置（BEFORE/AFTER CHAR/AN/EM） ──
        # 多个 anchor-based position 共用一个遍历：每命中一个锚点就插入，
        # 同 position 内按激活集顺序保持稳定。
        for position, ae_list in buckets.items():
            if position == WI_POSITION_AT_DEPTH:
                continue
            if position == WI_POSITION_OUTLET:
                # outlet 由 PromptRenderer 处理，这里不管
                continue

            anchor_info = _POSITION_ANCHOR.get(position)
            if anchor_info is None:
                logger.debug(
                    f"[WI Injector] position={position} 无对应锚点，跳过"
                )
                continue

            anchor_name, side = anchor_info
            result, new_history_start = _insert_around_anchor(
                result, anchor_name, side, ae_list, new_history_start
            )

        # ── AT_DEPTH 位置 ──
        at_depth_entries = buckets.get(WI_POSITION_AT_DEPTH, [])
        if at_depth_entries:
            result = _insert_at_depth(result, at_depth_entries, new_history_start)

        # ── 剥掉锚点标记 ──
        return WorldbookInjector._strip_anchors(result)

    @staticmethod
    def _strip_anchors(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            if ANCHOR_KEY in m:
                clean = {k: v for k, v in m.items() if k != ANCHOR_KEY}
                # 空 content 锚点（如 mes_example 占位）丢弃
                if not clean.get("content"):
                    continue
                out.append(clean)
            else:
                out.append(m)
        return out


def _insert_around_anchor(
    messages: list[dict],
    anchor_name: str,
    side: str,
    entries: list[ActiveEntry],
    history_start: int,
) -> tuple[list[dict], int]:
    """在指定锚点的前/后插入条目列表。返回 (新 messages, 新 history_start)。

    若锚点不存在，统一降级为 system 区末尾插入（紧邻 history 之前）。
    """
    anchor_idx = next(
        (i for i, m in enumerate(messages) if m.get(ANCHOR_KEY) == anchor_name),
        None,
    )

    if anchor_idx is None:
        # 降级：插到 system 区末尾（history 之前）
        insert_idx = history_start
    else:
        insert_idx = anchor_idx if side == "before" else anchor_idx + 1

    inserted = [
        {"role": ae.role, "content": ae.content}
        for ae in entries
    ]
    result = messages[:insert_idx] + inserted + messages[insert_idx:]

    # history_start 可能因前插而后移
    if insert_idx <= history_start:
        history_start += len(inserted)
    return result, history_start


def _insert_at_depth(
    messages: list[dict],
    entries: list[ActiveEntry],
    history_start: int,
) -> list[dict]:
    """按 entry.depth 将每条 entry 插入到历史末尾倒数第 N 条之前。

    depth=0 表示直接追加到末尾；depth >= history_length 表示插到 history 起点。
    同一 depth + role 的条目合并为多条独立消息，按激活顺序排列。
    """
    result = list(messages)
    # 倒序处理：先深的、后浅的，避免下标失效
    sorted_entries = sorted(entries, key=lambda ae: -ae.depth)

    for ae in sorted_entries:
        history_length = len(result) - history_start
        depth = max(0, ae.depth)
        if depth >= history_length:
            insert_idx = history_start
        else:
            insert_idx = len(result) - depth
        result.insert(insert_idx, {"role": ae.role, "content": ae.content})

    return result
