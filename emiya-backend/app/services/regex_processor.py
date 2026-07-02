# -*- coding: utf-8 -*-
"""正则后处理：应用 ST 预设/正则预设中的 regex_scripts。

使用 `regex` 模块（PyPI）替代 stdlib `re`，原因：
  - 支持不定长 lookbehind（JS ES2018+ 等价）
  - 支持 `(?<name>...)` / `\\k<name>` JS 风格命名组
  - 支持 `\\p{...}` Unicode 属性
  - 编译失败抛 `regex.error`，与 Python re 行为一致

JS ↔ Python 正则兼容层（详见 ADR-0015 / 0016）：
  - findRegex / replaceString 里的 JS 语义会被改写成 Python regex 模块语义
  - parse_js_regex 默认开启 ASCII flag，对齐 JS \\d/\\w/\\s/\\b 仅 ASCII 行为
  - substituteRegex 字段决定是否在 findRegex / replaceString 里跑 ST 宏
"""
from __future__ import annotations

import logging
from typing import Any

import regex

logger = logging.getLogger(__name__)

# JS regex flags → Python regex flags
_FLAG_MAP: dict[str, int] = {
    "i": regex.IGNORECASE,
    "m": regex.MULTILINE,
    "s": regex.DOTALL,
    # JS 的 g/u/y/d 在 Python 中均无直接对应：
    #   g  → sub/findall 默认全替；非 flag
    #   u  → Python 默认就开（再加无效）
    #   y  → sticky，无对应
    #   d  → match indices，无对应
}


# ─── substituteRegex 枚举（对齐 ST extensions/regex/engine.js:298-302） ───
SUBSTITUTE_NONE = 0       # 不跑宏
SUBSTITUTE_RAW = 1        # 跑宏，原值嵌入
SUBSTITUTE_ESCAPED = 2    # 跑宏，对结果做正则转义后嵌入


# ─── 前文/后文占位符（兼容 JS `$\`` / `$'`） ─────────────────────
# Python regex 没有原生"前文/后文"引用，但 sub 的 callable 形式可拿到
# match.string + start/end，所以完全可以等价实现：
#   _convert_replacement 输出阶段把 `$\`` 替换为 \x00JSPRE\x00
#                            把 `$'`  替换为 \x00JSPOST\x00
# RegexProcessor 调 sub 时检测占位符，存在时改走 callable 路径替换
# \x00 是控制字符，野生 ST 卡正文几乎不会出现，碰撞概率视为 0
_JS_PRE_TOKEN = "\x00JSPRE\x00"
_JS_POST_TOKEN = "\x00JSPOST\x00"


# ─── parse_js_regex ─────────────────────────────────────────────


def parse_js_regex(
    js_regex: str,
    *,
    ascii_word_char: bool = True,
) -> regex.Pattern | None:
    """将 JS 风格的正则字符串编译为 Python regex.Pattern。

    支持两种输入形式：
      - `/pattern/flags`  JS 包裹形式（带分隔符和可选标志）
      - 裸 pattern        无分隔符无标志

    Args:
        ascii_word_char:
            True 时给编译加 `regex.ASCII` flag，让 `\\d/\\w/\\s/\\b` 等元字符
            仅匹配 ASCII，与 JS 默认行为对齐（详见 ADR-0016）。
            False 时使用 Python regex 模块默认（Unicode-aware）。

    Returns:
        编译失败 / 输入无效时返回 None，调用方应跳过该脚本。
    """
    if not js_regex or not js_regex.strip():
        return None

    if js_regex.startswith("/"):
        last_slash = js_regex.rfind("/")
        if last_slash <= 0:
            return None
        pattern_str = js_regex[1:last_slash]
        flags_str = js_regex[last_slash + 1:]

        flags = 0
        for ch in flags_str:
            flags |= _FLAG_MAP.get(ch, 0)
    else:
        pattern_str = js_regex
        flags = 0

    if ascii_word_char:
        flags |= regex.ASCII

    try:
        return regex.compile(pattern_str, flags)
    except regex.error as e:
        logger.warning(f"无效的正则表达式: {js_regex!r} ({e})")
        return None


# ─── replacement 字符串：JS → Python ──────────────────────────────


def _convert_replacement(js_replacement: str) -> str:
    """把 JS 替换字符串改写成 Python regex.sub 接受的形式。

    JS 替换字符串语义 vs Python regex 模块差异（详见 ADR-0016）：

      JS                       Python regex
      ──────────────────────   ─────────────────────────
      $1 / $2 / ... / $99       \\g<1> / \\g<2> / ...
      $&  (whole match)         \\g<0>
      $$  (literal $)           $
      $<name> (named group)     \\g<name>
      $`  / $'  (pre/post)      ❌ 丢弃 + warning
      字面 \\                    \\\\
      字面 $（不属于上面任一种） $

    实现是一遍状态机扫描，确保"先转义字面 \\、再处理 $-占位"。
    朴素的 `regex.sub(r'\\$(\\d+)', r'\\\\\\1', text)` 做不到——它无法
    区分 "字面 \\" 与 "Python 引用前缀 \\"，且不处理 $&/$<>/$$ 等。
    """
    if not js_replacement:
        return js_replacement

    out: list[str] = []
    i = 0
    n = len(js_replacement)
    while i < n:
        ch = js_replacement[i]

        # ── 字面反斜杠：JS 里 \\ 即字面 \；Python 替换字符串里 \\ 才是字面 \
        if ch == "\\":
            out.append("\\\\")
            i += 1
            continue

        # ── $ 开头的占位符 ──
        if ch == "$":
            if i + 1 >= n:
                out.append("$")
                i += 1
                continue

            nxt = js_replacement[i + 1]

            # $$ → 字面 $
            if nxt == "$":
                out.append("$")
                i += 2
                continue

            # $& → 全匹配
            if nxt == "&":
                out.append("\\g<0>")
                i += 2
                continue

            # $` / $' → JS 的前文 / 后文。Python regex 没有原生引用，但 sub
            # 的 callable 形式拿得到 match.string + start/end，所以输出占位符
            # 留给 _do_sub_with_pre_post 时还原（见模块顶部 _JS_PRE_TOKEN 注释）
            if nxt == "`":
                out.append(_JS_PRE_TOKEN)
                i += 2
                continue
            if nxt == "'":
                out.append(_JS_POST_TOKEN)
                i += 2
                continue

            # $<name> → 命名组
            if nxt == "<":
                end = js_replacement.find(">", i + 2)
                if end != -1:
                    name = js_replacement[i + 2:end]
                    # 校验 name 是合法标识符；非法时按字面 $ 处理
                    if name and (name.isidentifier() or name.isdigit()):
                        out.append("\\g<" + name + ">")
                        i = end + 1
                        continue
                # 不闭合或非法 → 字面 $
                out.append("$")
                i += 1
                continue

            # $N / $NN → 组引用（JS 最多 $99；ST 用例里几乎都是个位数）
            if nxt.isdigit():
                j = i + 1
                # 尽量贪婪取数字（max 2 位，JS 上限）
                while j < n and js_replacement[j].isdigit() and (j - i) <= 2:
                    j += 1
                digits = js_replacement[i + 1:j]
                # 用 \g<N> 而非 \N，避免 \12 这种"组 1 + 字面 2 还是组 12"的歧义
                out.append("\\g<" + digits + ">")
                i = j
                continue

            # $X 不识别 → 字面 $
            out.append("$")
            i += 1
            continue

        # ── 其它字符原样输出 ──
        out.append(ch)
        i += 1

    return "".join(out)


# ─── substituteRegex 跑宏 + 转义 ──────────────────────────────────


def _escape_for_regex(text: str) -> str:
    """ST sanitizeRegexMacro 的 Python 对应实现。

    把可能在正则中具有特殊含义的字符转义；这是 substituteRegex=ESCAPED 模式
    下，把宏值安全嵌入 findRegex 的关键步骤。
    """
    return regex.escape(text or "")


def _maybe_run_macro(
    template_str: str,
    macro_scope: dict | None,
    *,
    escape: bool,
) -> str:
    """跑 ST 宏（{{user}} 等），可选对结果做正则转义。

    依赖 MacroEngine.render；macro_scope 为 None 时直接返回原串。
    跑宏失败时降级保留原串（不阻断主流程）。
    """
    if macro_scope is None or not template_str:
        return template_str
    try:
        from app.services.macro_engine import MacroEngine
        rendered = MacroEngine.render(template_str, macro_scope)
    except Exception:
        logger.exception("MacroEngine.render 失败，保留原串")
        return template_str
    if escape:
        return _escape_for_regex(rendered)
    return rendered


def _resolve_find_regex_string(
    script: dict,
    macro_scope: dict | None,
) -> str:
    """根据 substituteRegex 字段决定 findRegex 是否跑宏。

      0 / NONE     → 原样
      1 / RAW      → 跑宏，原值嵌入
      2 / ESCAPED  → 跑宏，结果用 regex.escape 处理后嵌入
    """
    find_regex = script.get("findRegex", "") or ""
    if not find_regex:
        return find_regex

    mode = int(script.get("substituteRegex", SUBSTITUTE_NONE) or 0)
    if mode == SUBSTITUTE_NONE:
        return find_regex
    if mode == SUBSTITUTE_RAW:
        return _maybe_run_macro(find_regex, macro_scope, escape=False)
    if mode == SUBSTITUTE_ESCAPED:
        return _maybe_run_macro(find_regex, macro_scope, escape=True)

    logger.warning(
        "未知的 substituteRegex 值 %r，按 NONE 处理", mode,
    )
    return find_regex


def _do_sub(
    pattern: regex.Pattern,
    replacement: str,
    text: str,
) -> str:
    """统一的 sub 入口；按需 fallback 到 callable 模式以支持 JS 前文/后文占位。

    无 `$\`` / `$'` 占位符时走 pattern.sub(str, str) 快路径（regex 模块内部
    高效解析 \\g<N>）；有占位符时走 callable 形式，每次匹配时用
    match.expand 处理标准组引用，再手动替换前/后文占位。

    所有逻辑都在 _convert_replacement 调用之后，replacement 此时已是
    Python 风格的 `\\g<N>` + 可能的占位符。
    """
    has_pre = _JS_PRE_TOKEN in replacement
    has_post = _JS_POST_TOKEN in replacement
    if not has_pre and not has_post:
        return pattern.sub(replacement, text)

    def _repl(m: regex.Match) -> str:
        # match.expand 用与 sub(str, ...) 一致的语法解析 \\g<N>、\\\\ 等
        out = m.expand(replacement)
        if has_pre:
            out = out.replace(_JS_PRE_TOKEN, m.string[:m.start()])
        if has_post:
            out = out.replace(_JS_POST_TOKEN, m.string[m.end():])
        return out

    return pattern.sub(_repl, text)


def _sanitize_invalid_group_refs(
    converted_replacement: str,
    pattern: regex.Pattern,
) -> str:
    """把 `\\g<N>` 中 N 超过 pattern.groups 的引用改回字面 `$N`。

    背景：`_convert_replacement` 不知道 findRegex 有几个 capture group——它对
    所有 `$N` 都生成 `\\g<N>`。JS 的 `String.replace` 遇到无效组引用会
    **保留字面 $N**；Python 的 `regex.sub` 会抛 `error: invalid group reference`。

    本函数在 sub 前 sanitize：N=0 (whole match) 永远合法；N>0 但超过
    pattern.groups 的，回滚为 `$N` 字面，对齐 JS 行为。
    """
    max_group = pattern.groups  # 不含 group 0

    def _fix(m: regex.Match) -> str:
        n = int(m.group(1))
        if n == 0 or n <= max_group:
            return m.group(0)
        # 超出 → 回滚字面
        return f"${n}"

    # 注意：这里要匹配的是 `\g<NUMBER>`——前面 _convert_replacement 已经
    # 把所有合法数字引用统一成 `\g<N>` 形式
    return regex.sub(r"\\g<(\d+)>", _fix, converted_replacement)


def _resolve_replace_string(
    script: dict,
    macro_scope: dict | None,
) -> str:
    """对 replaceString 跑宏（如果 substituteRegex != 0）。

    ST 行为：replaceString 同样会跑宏；ESCAPED 模式只影响 findRegex 的嵌入
    安全性，replaceString 不需要"转义为正则"，只需要把 {{user}} 等填回。
    """
    replace_string = script.get("replaceString", "") or ""
    if not replace_string:
        return replace_string

    mode = int(script.get("substituteRegex", SUBSTITUTE_NONE) or 0)
    if mode == SUBSTITUTE_NONE:
        return replace_string
    # RAW / ESCAPED 对 replaceString 一视同仁——只跑宏，不转义
    return _maybe_run_macro(replace_string, macro_scope, escape=False)


# ─── 公共类 ───────────────────────────────────────────────────────


class RegexProcessor:
    """对消息列表 / 单条文本应用 regex_scripts。"""

    @staticmethod
    def apply_prompt_only(
        messages: list[dict],
        scripts: list[dict],
        *,
        macro_scope: dict | None = None,
    ) -> list[dict]:
        """对 messages 应用所有 promptOnly=true 的脚本（prompt 阶段）。

        返回处理后的消息列表（不修改原列表）。
        """
        result = [dict(m) for m in messages]

        applicable = [
            s for s in scripts
            if not s.get("disabled", False) and s.get("promptOnly", False)
        ]
        if not applicable:
            return result

        for script in applicable:
            find_str = _resolve_find_regex_string(script, macro_scope)
            pattern = parse_js_regex(find_str)
            if pattern is None:
                continue
            replace_raw = _resolve_replace_string(script, macro_scope)
            replacement = _convert_replacement(replace_raw)
            # 把 replacement 里超出 pattern.groups 的 \g<N> 还原为字面 $N（JS 行为）
            replacement = _sanitize_invalid_group_refs(replacement, pattern)
            placement = script.get("placement", [])
            min_depth = script.get("minDepth")
            max_depth = script.get("maxDepth")

            for idx, msg in enumerate(result):
                if not _should_apply(idx, msg, len(result), placement, min_depth, max_depth):
                    continue
                try:
                    msg["content"] = _do_sub(pattern, replacement, msg["content"])
                except Exception:
                    logger.warning(
                        "apply_prompt_only: script '%s' failed on message #%d",
                        script.get("scriptName", "?"), idx,
                    )

        return result

    @staticmethod
    def apply_reply_to_text(
        text: str,
        scripts: list[dict],
        *,
        macro_scope: dict | None = None,
    ) -> str:
        """对单条 assistant 文本跑传入的 AI_OUTPUT 阶段脚本（reply 阶段）。

        与 apply_prompt_only 不同：输入是单串，对应 ST placement=2 (AI_OUTPUT)
        语义，由 message_pipeline 在 assistant 文本"持久化前"调用。

        ⚠️ 视图过滤（promptOnly / markdownOnly）由调用方完成：message_pipeline 会
        分别传入"prompt 真相版"（not markdownOnly）与"显示版"（not promptOnly）两个
        子集（详见 docs/mvu/adr/0003 双管线）。这里只剔除 disabled，忠实应用传入集合。

        depth / placement 限制此处不生效——单串没有"楼层"概念。
        """
        if not text:
            return text
        applicable = [
            s for s in scripts
            if not s.get("disabled", False)
        ]
        if not applicable:
            return text

        result = text
        for script in applicable:
            find_str = _resolve_find_regex_string(script, macro_scope)
            pattern = parse_js_regex(find_str)
            if pattern is None:
                continue
            replace_raw = _resolve_replace_string(script, macro_scope)
            replacement = _convert_replacement(replace_raw)
            # 把 replacement 里超出 pattern.groups 的 \g<N> 还原为字面 $N（JS 行为）
            replacement = _sanitize_invalid_group_refs(replacement, pattern)
            try:
                result = _do_sub(pattern, replacement, result)
            except Exception:
                logger.warning(
                    "apply_reply_to_text: script '%s' failed",
                    script.get("scriptName", "?"),
                )
        return result


def _should_apply(
    idx: int,
    msg: dict,
    total: int,
    placement: list[int],
    min_depth: int | None,
    max_depth: int | None,
) -> bool:
    """判断脚本是否应该应用于第 idx 条消息。

    placement: 0=system区 / 1=末尾 / 2=聊天历史
    简单 heuristic: system role 视为 placement 0；其它消息 placement 2
    """
    role = msg.get("role", "")
    position = 0 if role == "system" else 2

    if position not in placement:
        return False

    # Depth check — 从末尾计数（depth 0 = 最后一条）
    if position == 2 and (min_depth is not None or max_depth is not None):
        depth_from_end = total - 1 - idx
        if min_depth is not None and depth_from_end < min_depth:
            return False
        if max_depth is not None and depth_from_end > max_depth:
            return False

    return True
