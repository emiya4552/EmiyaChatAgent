# -*- coding: utf-8 -*-
"""预设注入器：按 position/depth 将 prompt 插入到消息列表中。"""
import logging
from app.services.ejs_engine import EJSEngine
from app.services.macro_engine import MacroEngine

logger = logging.getLogger(__name__)


class PresetInjector:
    """将 ST break 预设的 prompts[] 注入到消息列表。"""

    @staticmethod
    def inject(
        messages: list[dict],
        preset: dict,
        scope: dict | None = None,
        run_ejs: bool = True,
    ) -> list[dict]:
        """按 injection_position/depth 注入所有 enabled prompt。

        messages: 当前完整消息列表（含 system 区 + history）
        preset: 预设 JSON dict（含 prompts[] 数组）
        scope: MacroEngine dual-bucket 变量作用域，详见 docs/adr/0007
        run_ejs: 是否执行 MVU/EJS 模板层。关闭 MVU 兼容时传 False。

        返回新的消息列表（不修改原列表）。
        """
        # scope 兼容：None / plain dict / dual-bucket 都接受
        # MacroEngine.render 内部会做 coerce

        # 支持两种格式: prompts[] (原始ST) 或 slots{} (导入转换后)
        prompts = preset.get("prompts")
        if prompts is None:
            slots = preset.get("slots", {})
            prompts = list(slots.values())
        if not prompts:
            return list(messages)

        # 找到 history 起始位置（第一条非 system 消息）
        history_start = 0
        for i, m in enumerate(messages):
            if m.get("role") != "system":
                history_start = i
                break
        else:
            history_start = len(messages)

        # 按 injection_order 排序
        sorted_prompts = sorted(prompts, key=lambda p: p.get("injection_order", 100))

        result = list(messages)
        pos1_insert_at = 0  # position=1 按顺序插入的偏移

        for prompt in sorted_prompts:
            if not prompt.get("enabled", True):
                continue

            # ST 内部槽位标记 — 不注入
            if prompt.get("marker"):
                continue

            content = prompt.get("content", "")
            if not content:
                continue

            # EJS 先跑（MVU 兼容，详见 ADR-0010），再跑 MacroEngine
            ejs_scope = (scope or {}).get("local") or {} if isinstance(scope, dict) else {}
            if run_ejs:
                content = EJSEngine.render(content, ejs_scope)
            rendered = MacroEngine.render(content, scope)
            if not rendered.strip():
                continue

            role = prompt.get("role", "system")
            position = prompt.get("injection_position", 0)
            depth = prompt.get("injection_depth", 4)

            inserted = {"role": role, "content": rendered}

            if position == 1:
                # ABSOLUTE: 注入到 system 区头部，按 order 排列
                result.insert(pos1_insert_at, inserted)
                pos1_insert_at += 1
                history_start += 1

            elif position == 0:
                # RELATIVE: 注入到 system 区末尾（history 之前）
                insert_idx = history_start
                result.insert(insert_idx, inserted)
                history_start += 1

            elif position == 2:
                # 注入到聊天历史的特定深度
                history_length = len(result) - history_start
                if depth >= history_length:
                    # 溢出 → system 区末尾
                    result.insert(history_start, inserted)
                    history_start += 1
                else:
                    # 从末尾倒数 depth 条
                    target_idx = len(result) - depth
                    result.insert(target_idx, inserted)

        return result
