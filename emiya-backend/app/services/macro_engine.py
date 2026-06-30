# -*- coding: utf-8 -*-
"""ST 宏变量引擎：解析并渲染 prompt 文本中的 {{macro}}。

支持的宏（详见 docs/adr/0007、ADR-0010）：
- 变量类：setvar/getvar/addvar/incvar/decvar/pick
  + global 变体：setglobalvar/getglobalvar
- MVU 兼容：format_message_variable / getMessageVariable / getMsgVar
  （在 scope["local"] 的点路径取值，嵌套 dict/list 用 YAML 缩进输出）
- 控制流：{{if X}}body{{else}}else_body{{/if}}  (L1 真值 + L2 等值)
- 随机：random/roll/dice/floating
- 辅助：trim、注释 //、名字宏 {{user}} {{char}}

scope 规范：
    {
      "local":  {name: str, ...},  # 对话级（Conversation.variables）
      "global": {name: str, ...},  # 用户级（User.global_variables）
      "names":  {"user": "...", "char": "..."},  # 名字宏数据源
    }

向后兼容：如果传入的 scope 不带 local/global/names 任一键，则视为旧式
plain dict 并把它当作 local 桶（PresetInjector 老调用走这条路径）。
"""
import re
import random as _random_module

_MACRO_RE = re.compile(r"\{\{(.+?)\}\}", re.DOTALL)


def _coerce_scope(scope: dict | None) -> dict:
    """归一化 scope 为 dual-bucket 形态。原地补全缺失桶。"""
    if scope is None:
        return {"local": {}, "global": {}, "names": {}}
    has_bucket = any(k in scope for k in ("local", "global", "names"))
    if not has_bucket:
        # 旧式 plain dict：当作 local 桶，但内容写回到调用方传入的 dict
        return {"local": scope, "global": {}, "names": {}}
    scope.setdefault("local", {})
    scope.setdefault("global", {})
    scope.setdefault("names", {})
    return scope


def _is_truthy(s: str) -> bool:
    """真值判定：空 / "0" / "false" / "False" / "null" → false，其余 → true。"""
    if s is None:
        return False
    t = s.strip()
    if not t:
        return False
    return t.lower() not in ("0", "false", "null", "none")


def _resolve_value(expr: str, scope: dict) -> str:
    """求一个 cond 子表达式的值，用于 if 比较或真值检测。

    支持：
      - getvar::name        → local[name]
      - getglobalvar::name  → global[name]
      - 裸 name             → local[name]（兼容 ST `{{if myvar}}`）
      - 其他字面值          → 原样返回（去掉首尾空白）
    """
    expr = expr.strip()
    if expr.startswith("getvar::"):
        return str(scope["local"].get(expr[len("getvar::"):].strip(), ""))
    if expr.startswith("getglobalvar::"):
        return str(scope["global"].get(expr[len("getglobalvar::"):].strip(), ""))
    # 兼容：if 后裸名 → local
    if expr.isidentifier():
        return str(scope["local"].get(expr, ""))
    # 字面值（数字、字符串）
    return expr


def _eval_condition(cond: str, scope: dict) -> bool:
    """判定 if 条件。L1 真值或 L2 等值。"""
    if "==" in cond:
        left, _, right = cond.partition("==")
        return _resolve_value(left, scope) == _resolve_value(right, scope)
    return _is_truthy(_resolve_value(cond, scope))


def _resolve_local_path(local_bucket: dict, path: str):
    """在 local 桶上做点路径取值（用于 MVU 的 stat_data.a.b.c 等访问）。

    缺失任意一段返回 None。
    """
    cur = local_bucket
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


def _format_mvu_value(value) -> str:
    """把 MVU 变量值格式化为 LLM 友好的字符串。

    - None  → ""（避免污染 prompt）
    - 字符串 / 数字 / 布尔 → str()
    - dict / list / 嵌套 → YAML 多行缩进（保留中文）
    """
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        import yaml
        return yaml.safe_dump(
            value,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ).rstrip()
    except Exception:
        return str(value)


# ─── token 化 ────────────────────────────────────────────────────


def _tokenize(text: str) -> list[tuple]:
    """把文本切成 [(kind, payload), ...] token 流。

    kind ∈ {"TEXT", "IF", "ELSE", "ENDIF", "MACRO"}。
    """
    tokens: list[tuple] = []
    pos = 0
    for match in _MACRO_RE.finditer(text):
        if match.start() > pos:
            tokens.append(("TEXT", text[pos:match.start()]))
        pos = match.end()
        inner = match.group(1).strip()
        lower = inner.lower()
        if lower.startswith("if ") or lower.startswith("if\t"):
            tokens.append(("IF", inner[3:].strip()))
        elif lower == "if":  # 空 if（罕见，跳过）
            tokens.append(("IF", ""))
        elif lower == "else":
            tokens.append(("ELSE", None))
        elif lower in ("/if", "endif"):
            tokens.append(("ENDIF", None))
        else:
            tokens.append(("MACRO", inner))
    if pos < len(text):
        tokens.append(("TEXT", text[pos:]))
    return tokens


# ─── 简单宏（非 if）执行 ─────────────────────────────────────────


def _exec_simple_macro(inner: str, scope: dict, accumulated_out: list[str]) -> str | None:
    """执行非控制流宏。返回该宏对应的输出字符串（可能 ""），未识别则返回 None。

    accumulated_out 用于 trim 宏 in-place 修改已累积输出。
    """
    parts = inner.split("::")
    name = parts[0].strip()

    if name.startswith("//"):
        return ""

    if name == "random":
        opts = parts[1:]
        return _random_module.choice(opts) if opts else ""

    if name == "setvar":
        var_name = parts[1].strip() if len(parts) > 1 else ""
        value = parts[2] if len(parts) > 2 else ""
        if var_name:
            if value:
                scope["local"][var_name] = value
            else:
                scope["local"].pop(var_name, None)
        return ""

    if name == "getvar":
        var_name = parts[1].strip() if len(parts) > 1 else ""
        return str(scope["local"].get(var_name, ""))

    if name == "addvar":
        var_name = parts[1].strip() if len(parts) > 1 else ""
        if var_name and len(parts) > 2:
            existing = scope["local"].get(var_name, "")
            scope["local"][var_name] = (existing + parts[2]) if existing else parts[2]
        return ""

    if name == "incvar":
        var_name = parts[1].strip() if len(parts) > 1 else ""
        if var_name:
            cur = scope["local"].get(var_name, 0)
            try:
                cur_n = int(cur)
            except (TypeError, ValueError):
                cur_n = 0
            new_n = cur_n + 1
            scope["local"][var_name] = str(new_n)
            return str(new_n)
        return ""

    if name == "decvar":
        var_name = parts[1].strip() if len(parts) > 1 else ""
        if var_name:
            cur = scope["local"].get(var_name, 0)
            try:
                cur_n = int(cur)
            except (TypeError, ValueError):
                cur_n = 0
            new_n = cur_n - 1
            scope["local"][var_name] = str(new_n)
            return str(new_n)
        return ""

    if name == "setglobalvar":
        var_name = parts[1].strip() if len(parts) > 1 else ""
        value = parts[2] if len(parts) > 2 else ""
        if var_name:
            if value:
                scope["global"][var_name] = value
            else:
                scope["global"].pop(var_name, None)
        return ""

    if name == "getglobalvar":
        var_name = parts[1].strip() if len(parts) > 1 else ""
        return str(scope["global"].get(var_name, ""))

    # MVU 兼容（详见 ADR-0010）：从 scope["local"] 的点路径取值并格式化
    # 嵌套 dict/list 用 YAML 多行缩进，便于 LLM 阅读；缺失返回空
    # 别名：getMessageVariable / getMsgVar 同义于 ST 端 bundle.js 行为
    if name in ("format_message_variable", "getMessageVariable", "getMsgVar"):
        path = parts[1].strip() if len(parts) > 1 else ""
        if not path:
            return ""
        value = _resolve_local_path(scope["local"], path)
        return _format_mvu_value(value)

    if name == "user":
        return str(scope["names"].get("user", ""))

    if name == "char":
        return str(scope["names"].get("char", ""))

    if name == "roll":
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        return str(_random_module.randint(1, max(n, 1)))

    if name == "dice":
        spec = parts[1] if len(parts) > 1 else "1d6"
        n_str, _, m_str = spec.partition("d")
        n = int(n_str) if n_str.isdigit() else 1
        m = int(m_str) if m_str.isdigit() else 6
        total = sum(_random_module.randint(1, m) for _ in range(max(n, 1)))
        return str(total)

    if name == "pick":
        var_name = parts[1].strip() if len(parts) > 1 else ""
        if var_name and var_name in scope["local"]:
            return scope["local"][var_name]
        if len(parts) > 2:
            picked = _random_module.choice(parts[2:])
            if var_name:
                scope["local"][var_name] = picked
            return picked
        return ""

    if name == "floating":
        opts = parts[1:]
        return _random_module.choice(opts) if opts else ""

    if name == "trim":
        accumulated = "".join(accumulated_out)
        accumulated_out.clear()
        accumulated_out.append(accumulated.rstrip())
        return ""

    return None  # 未识别


# ─── 渲染主循环（支持 if 嵌套） ──────────────────────────────────


def _render_tokens(tokens: list[tuple], idx: int, scope: dict, stop_on: set) -> tuple[str, int]:
    """从 idx 开始渲染 tokens，直到遇到 stop_on 中的 token 类型或结束。

    返回 (rendered_string, next_idx_after_stop_token)。
    """
    out: list[str] = []
    i = idx
    while i < len(tokens):
        kind, payload = tokens[i]
        if kind in stop_on:
            return "".join(out), i
        if kind == "TEXT":
            out.append(payload)
            i += 1
            continue
        if kind == "IF":
            cond = payload
            # 渲染 then 分支
            then_str, j = _render_tokens(tokens, i + 1, scope, {"ELSE", "ENDIF"})
            # 是否有 else
            else_str = ""
            if j < len(tokens) and tokens[j][0] == "ELSE":
                else_str, j = _render_tokens(tokens, j + 1, scope, {"ENDIF"})
            # 跳过 ENDIF
            if j < len(tokens) and tokens[j][0] == "ENDIF":
                j += 1
            if _eval_condition(cond, scope):
                out.append(then_str)
            else:
                out.append(else_str)
            i = j
            continue
        if kind in ("ELSE", "ENDIF"):
            # 孤立的 ELSE/ENDIF（无匹配 IF）→ 原样保留
            label = "else" if kind == "ELSE" else "/if"
            out.append("{{" + label + "}}")
            i += 1
            continue
        if kind == "MACRO":
            res = _exec_simple_macro(payload, scope, out)
            if res is None:
                # 未识别宏 → 原样保留
                out.append("{{" + payload + "}}")
            else:
                out.append(res)
            i += 1
            continue
        i += 1
    return "".join(out), i


class MacroEngine:
    """ST 宏渲染器。线程不安全（依赖 random + scope mutation）。"""

    @staticmethod
    def render(text: str, scope: dict | None = None) -> str:
        """解析 text 中的所有 {{macro}} 并返回渲染后的字符串。

        Args:
            text: 包含宏占位符的文本
            scope: dual-bucket 变量作用域，详见模块 docstring。setvar/incvar
                等宏会原地修改 scope["local"] / scope["global"]，供下游写回 DB。
        """
        if not text:
            return text
        scope = _coerce_scope(scope)
        tokens = _tokenize(text)
        rendered, _ = _render_tokens(tokens, 0, scope, set())
        return rendered
