# -*- coding: utf-8 -*-
"""世界书扫描器：关键词匹配 + 预算筛选 → 激活集。

参见：
  docs/adr/0001-worldbook-as-independent-module.md (L1-L5 触发机制)
  CONTEXT.md "世界书 / Activated Entries"
"""
import logging
from dataclasses import dataclass, field
from typing import Iterable

from app.config import settings
from app.models.worldbook import (
    WI_LOGIC_AND_ALL,
    WI_LOGIC_AND_ANY,
    WI_LOGIC_NOT_ALL,
    WI_LOGIC_NOT_ANY,
)
from app.services.regex_processor import parse_js_regex
from app.services.token_budget import resolve_worldbook_budget
from app.utils.token_counter import count_tokens

logger = logging.getLogger(__name__)


@dataclass
class ActiveEntry:
    """扫描器产出的单条激活条目。

    包含原始 entry 字典 + 元信息（来自哪本书、最终生效的 position/depth/order）。
    Injector 直接消费这个对象。
    """

    entry: dict
    worldbook_id: str
    worldbook_name: str
    # 冗余出来便于排序/调度
    position: int
    depth: int
    order: int
    role: str
    outlet_name: str | None
    content: str
    entry_lookup: dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        comment = self.entry.get("comment") or self.entry.get("content", "")[:20]
        return f"<ActiveEntry uid={self.entry.get('uid')} '{comment}'>"


# ─── 关键词匹配 ───────────────────────────────────────────────────


def _match_key(
    haystack: str,
    needle: str,
    case_sensitive: bool,
    match_whole_words: bool,
    use_regex: bool = False,
) -> bool:
    """单关键词匹配。

    优先级：
      1. `use_regex=True` → 整个 needle 当 JS 正则（无需 /…/flags 包裹）
      2. needle 形如 `/pattern/flags` → JS 正则
      3. 否则按文本匹配（受 match_whole_words 控制）
    """
    if not needle:
        return False

    js_regex = None
    if use_regex:
        # entry.use_regex=true 时 keys 整体当正则；先试 /…/flags，否则裸字符串当 pattern
        js_regex = parse_js_regex(needle)
    elif needle.startswith("/"):
        js_regex = parse_js_regex(needle)
    if js_regex is not None:
        return bool(js_regex.search(haystack))

    target_haystack = haystack if case_sensitive else haystack.lower()
    target_needle = needle if case_sensitive else needle.lower()

    if match_whole_words:
        # 简易实现：单词由空白分隔，关键词若含空白则退化为子串匹配
        if " " in target_needle:
            return target_needle in target_haystack
        import re

        return bool(
            re.search(
                r"(?:^|\W)" + re.escape(target_needle) + r"(?:$|\W)",
                target_haystack,
            )
        )

    return target_needle in target_haystack


def _entry_resolve(entry: dict, book_default: dict, key: str, fallback):
    """单字段三层解析：entry > book > fallback。"""
    v = entry.get(key)
    if v is not None:
        return v
    v = book_default.get(key)
    if v is not None:
        return v
    return fallback


def _check_entry_keys(entry: dict, scan_buffer: str, book_default: dict) -> bool:
    """对单条 entry 做主关键词 + 副关键词 + selective_logic 综合判定。"""
    case_sensitive = _entry_resolve(entry, book_default, "case_sensitive", False)
    match_whole_words = _entry_resolve(entry, book_default, "match_whole_words", False)
    # v3 spec：entry.use_regex=true 时 key/keysecondary 元素整体按 JS 正则解释
    use_regex = bool(entry.get("use_regex", False))

    keys = entry.get("key") or []
    if not keys:
        return False

    primary_hit = any(
        _match_key(scan_buffer, k, case_sensitive, match_whole_words, use_regex)
        for k in keys
    )
    if not primary_hit:
        return False

    keys_secondary = entry.get("keysecondary") or []
    if not keys_secondary:
        return True

    selective_logic = int(entry.get("selective_logic", WI_LOGIC_AND_ANY))
    matches = [
        _match_key(scan_buffer, k, case_sensitive, match_whole_words, use_regex)
        for k in keys_secondary
    ]

    if selective_logic == WI_LOGIC_AND_ANY:
        return any(matches)
    if selective_logic == WI_LOGIC_AND_ALL:
        return all(matches)
    if selective_logic == WI_LOGIC_NOT_ANY:
        return not any(matches)
    if selective_logic == WI_LOGIC_NOT_ALL:
        return not all(matches)
    # 未知逻辑值，按 AND_ANY 兜底
    return any(matches)


# ─── 扫描主入口 ──────────────────────────────────────────────────


def _build_scan_buffer(
    history_messages: list[dict],
    depth: int,
) -> str:
    """取最近 `depth` 条消息拼成扫描缓冲区。messages 顺序：旧 → 新。"""
    if depth <= 0 or not history_messages:
        return ""
    slice_ = history_messages[-depth:]
    # 用 \x01 分隔，避免跨消息边界误匹配（同 ST）
    return "\x01" + "\n\x01".join((m.get("content") or "").strip() for m in slice_)


def _build_entry_lookup(entries: Iterable[dict]) -> dict[str, str]:
    """为一本世界书构建一个“按条目名取条目内容”的查找表，供受控版 getwi(null, "entry name") 使用"""
    lookup: dict[str, str] = {}
    for entry in entries:
        if not entry.get("enabled", True) or entry.get("disable") is True:
            continue
        content = entry.get("content") or ""
        if not content.strip():
            continue
        for key in (
            entry.get("comment"),
            entry.get("name"),
            entry.get("title"),
            entry.get("uid"),
        ):
            if key is not None:
                lookup.setdefault(str(key), content)
    return lookup


def scan_worldbook(
    worldbooks: list[dict],
    history_messages: list[dict],
    chat_config: dict,
) -> list[ActiveEntry]:
    """扫描所有绑定的世界书，返回激活集。

    Args:
        worldbooks: list of {id, name, scan_depth, case_sensitive, match_whole_words, entries[], extensions}
        history_messages: 聊天历史，旧 → 新顺序（dict 含 role, content）
        chat_config: 对话的 chat_config（读 worldbook_budget_pct / cap / max_context）

    Returns:
        激活的 ActiveEntry 列表，已按 order 降序排序。
        预算耗尽后只保留 ignore_budget=True 的额外条目。
    """
    if not worldbooks:
        return []

    # ── 预算计算 ──
    budget_info = resolve_worldbook_budget(chat_config)
    budget = int(budget_info["budget"])
    overflow_alert = bool(budget_info["overflow_alert"])

    candidates: list[tuple[int, int, ActiveEntry]] = []
    """各候选条目，元组形如 (order, attach_index_in_book, ActiveEntry)。
    attach_index 用于同 order 时的稳定排序。"""

    for book in worldbooks:
        book_id = str(book.get("id"))
        book_name = book.get("name", "")
        entries = book.get("entries", []) or []
        entry_lookup = _build_entry_lookup(entries)
        book_default = {
            "scan_depth": book.get(
                "scan_depth", settings.WORLDBOOK_DEFAULT_SCAN_DEPTH
            ),
            "case_sensitive": book.get("case_sensitive", False),
            "match_whole_words": book.get("match_whole_words", False),
        }

        for idx, entry in enumerate(entries):
            if not entry.get("enabled", True):
                continue
            if entry.get("disable") is True:  # ST 兼容字段名
                continue

            content = entry.get("content") or ""
            if not content.strip():
                continue

            activated = False
            if entry.get("constant"):
                activated = True
            else:
                scan_depth = int(
                    _entry_resolve(
                        entry,
                        book_default,
                        "scan_depth",
                        settings.WORLDBOOK_DEFAULT_SCAN_DEPTH,
                    )
                )
                scan_buffer = _build_scan_buffer(history_messages, scan_depth)
                if scan_buffer:
                    activated = _check_entry_keys(entry, scan_buffer, book_default)

            if not activated:
                continue

            ae = ActiveEntry(
                entry=entry,
                worldbook_id=book_id,
                worldbook_name=book_name,
                position=int(entry.get("position", 0)),
                depth=int(entry.get("depth", 4)),
                order=int(entry.get("order", 100)),
                role=str(entry.get("role", "system")),
                outlet_name=entry.get("outlet_name") or None,
                content=content,
                entry_lookup=entry_lookup,
            )
            candidates.append((ae.order, idx, ae))

    # ST 排序：order 降序；同 order 按书内插入顺序
    candidates.sort(key=lambda t: (-t[0], t[1]))

    # ── 预算筛选 ──
    activated_list: list[ActiveEntry] = []
    used_tokens = 0
    skipped = 0
    for _order, _idx, ae in candidates:
        entry_tokens = count_tokens(ae.content)
        if not ae.entry.get("ignore_budget"):
            if used_tokens + entry_tokens >= budget:
                skipped += 1
                continue
        activated_list.append(ae)
        used_tokens += entry_tokens

    if skipped > 0 and overflow_alert:
        logger.warning(
            f"[WI] 预算 {budget} tokens 达到上限，跳过 {skipped} 条非豁免条目"
        )

    logger.info(
        f"[WI] 激活 {len(activated_list)} 条 / 候选 {len(candidates)} 条；"
        f"用 {used_tokens}/{budget} tokens"
    )
    return activated_list
