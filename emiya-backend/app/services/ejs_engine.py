# -*- coding: utf-8 -*-
"""EJS 极简引擎（用于 MVU 卡兼容，详见 ADR-0010）。

只支持四类语法：
    1. 条件块  <%_ if (cond) { _%> body <%_ } _%>
       含可选 else: <%_ if (cond) { _%> a <%_ } else { _%> b <%_ } _%>
    2. 表达式插值  <%= expr %>   /  <%- expr %>  （v0 不区分 escape）
    3. getvar('a.b.c') 调用：在 variables 上做点路径取值
    4. 二元/逻辑算子：>  <  >=  <=  ==  ===  !=  !==  &&  ||  ! 及括号

设计取舍：
- 拒绝引入 EJS / Jinja2 库 —— v0 范围窄，自研更稳。
- 表达式求值不调 eval()。先用字符串预处理把 JS 算子翻译为 Python（`===` → `==`,
  `&&` → ` and ` 等，且尊重字符串字面量边界），然后 `ast.parse(..., mode="eval")`
  得到 AST 树，自己遍历求值，节点白名单严格限制（无 Attribute、无 Lambda、无 Import）。
- 遇到不识别的 EJS 块（如 `<% var x = ... %>` 变量赋值）**原样保留**，不抛错；
  方便兼容性递进，也方便日志里观察"什么语法漏支持"。

求值上下文（scope）形态：
    scope = {
        "stat_data": {...},
        "initialized_lorebooks": {...},
        "schema": "...",
    }
即镜像 ST chat_metadata.variables[i] 的结构（详见 ADR-0010 决定 2）。
"""
from __future__ import annotations

import ast
import logging
import re

logger = logging.getLogger(__name__)


# ─── Tokenizer ─────────────────────────────────────────────────────

# 一个 EJS 块的边界：`<%`(可选 `_` / `=` / `-`) 任意正文 (可选 `_` ) `%>`
_BLOCK_RE = re.compile(r"<%(_|=|-)?(.*?)(_)?%>", re.DOTALL)

# 块的语义分类
_T_TEXT = "TEXT"
_T_IF = "IF"
_T_ELSE = "ELSE"
_T_ENDIF = "ENDIF"
_T_EXPR = "EXPR"
_T_RAW = "RAW"  # 不识别的块，原样输出（含起止 `<%...%>`）


_IF_RE = re.compile(r"^\s*if\s*\((.*)\)\s*\{\s*$", re.DOTALL)
_ELSE_RE = re.compile(r"^\s*\}\s*else\s*\{\s*$")
_ENDIF_RE = re.compile(r"^\s*\}\s*$")


def _classify_block(prefix: str | None, body: str, raw: str) -> tuple[str, str]:
    """对单个 `<%...%>` 块分类。返回 (kind, payload)。

    prefix 是开头 `<%` 之后的修饰符 (`_` / `=` / `-` / None)；
    body 是内部正文。
    """
    if prefix in ("=", "-"):
        return _T_EXPR, body.strip()
    # 控制流：if / } else { / }
    if _IF_RE.match(body):
        return _T_IF, _IF_RE.match(body).group(1)
    if _ELSE_RE.match(body):
        return _T_ELSE, ""
    if _ENDIF_RE.match(body):
        return _T_ENDIF, ""
    # 其他 `<% ... %>` 块（含变量赋值、循环等 v0 不支持的）
    return _T_RAW, raw


def _tokenize(text: str) -> list[tuple[str, str]]:
    """切 EJS 文本为 token 流。

    返回 [(kind, payload), ...]，kind ∈ {TEXT, IF, ELSE, ENDIF, EXPR, RAW}。
    """
    tokens: list[tuple[str, str]] = []
    pos = 0
    for m in _BLOCK_RE.finditer(text):
        if m.start() > pos:
            tokens.append((_T_TEXT, text[pos:m.start()]))
        pos = m.end()
        kind, payload = _classify_block(m.group(1), m.group(2), m.group(0))
        tokens.append((kind, payload))
    if pos < len(text):
        tokens.append((_T_TEXT, text[pos:]))
    return tokens


# ─── 表达式求值 ─────────────────────────────────────────────────────

# JS → Python 算子翻译表。注意顺序：先长后短，避免 `===` 被 `==` 提前匹配。
_OP_REPLACEMENTS = [
    ("===", "=="),
    ("!==", "!="),
    ("&&", " and "),
    ("||", " or "),
    # `!` 单独处理（避免误伤 `!=`）；下面在 translator 里特判
]


def _translate_js_expr(expr: str) -> str:
    """把 JS 表达式语法翻译为 Python 表达式语法，但**尊重字符串字面量边界**。

    例如 `getvar('a') === "x"` → `getvar('a') == "x"`
    """
    out: list[str] = []
    i = 0
    in_str: str | None = None  # 当前在哪种引号内
    while i < len(expr):
        ch = expr[i]
        if in_str is None:
            if ch in ("'", '"'):
                in_str = ch
                out.append(ch)
                i += 1
                continue
            # 试匹配多字符算子
            replaced = False
            for js_op, py_op in _OP_REPLACEMENTS:
                if expr.startswith(js_op, i):
                    out.append(py_op)
                    i += len(js_op)
                    replaced = True
                    break
            if replaced:
                continue
            # 单字符 `!`：必须不是 `!=` 的开头
            if ch == "!" and not (i + 1 < len(expr) and expr[i + 1] == "="):
                out.append(" not ")
                i += 1
                continue
            # 关键字 true/false/null（标识符边界）
            if expr[i:i + 4] == "true" and (i + 4 == len(expr) or not expr[i + 4].isalnum() and expr[i + 4] != "_"):
                out.append("True")
                i += 4
                continue
            if expr[i:i + 5] == "false" and (i + 5 == len(expr) or not expr[i + 5].isalnum() and expr[i + 5] != "_"):
                out.append("False")
                i += 5
                continue
            if expr[i:i + 4] == "null" and (i + 4 == len(expr) or not expr[i + 4].isalnum() and expr[i + 4] != "_"):
                out.append("None")
                i += 4
                continue
            out.append(ch)
            i += 1
        else:
            # 在字符串内：原样复制，处理转义
            out.append(ch)
            if ch == "\\" and i + 1 < len(expr):
                out.append(expr[i + 1])
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
    return "".join(out)


def _resolve_dot_path(scope: dict, path: str):
    """在 scope 上做点路径取值。缺失任意一级返回 None。"""
    cur = scope
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


def _eval_ast(node, scope: dict):
    """安全求值：仅允许白名单 AST 节点。"""
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body, scope)
    if isinstance(node, ast.Constant):
        return node.value
    # 字面量 list / tuple
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval_ast(e, scope) for e in node.elts]
    # 比较
    if isinstance(node, ast.Compare):
        left = _eval_ast(node.left, scope)
        for op, right_node in zip(node.ops, node.comparators):
            right = _eval_ast(right_node, scope)
            if not _do_compare(left, op, right):
                return False
            left = right
        return True
    # 布尔
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for v in node.values:
                r = _eval_ast(v, scope)
                if not _truthy(r):
                    return False
            return True
        if isinstance(node.op, ast.Or):
            for v in node.values:
                r = _eval_ast(v, scope)
                if _truthy(r):
                    return r
            return False
    if isinstance(node, ast.UnaryOp):
        operand = _eval_ast(node.operand, scope)
        if isinstance(node.op, ast.Not):
            return not _truthy(operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        raise EJSEvalError(f"不允许的一元算子: {type(node.op).__name__}")
    if isinstance(node, ast.BinOp):
        left = _eval_ast(node.left, scope)
        right = _eval_ast(node.right, scope)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right if right else 0
        if isinstance(node.op, ast.Mod):
            return left % right if right else 0
        raise EJSEvalError(f"不允许的二元算子: {type(node.op).__name__}")
    # 函数调用：仅 getvar / getglobalvar / getchatvar 等若干白名单
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise EJSEvalError("仅支持顶级函数名调用")
        fname = node.func.id
        args = [_eval_ast(a, scope) for a in node.args]
        return _call_builtin(fname, args, scope)
    # 标识符：v0 只允许 true/false/null（已在翻译阶段转 True/False/None）以外的裸名
    # 视为字面字符串（避免一些 EJS 表达式里裸引用变量名时炸）
    if isinstance(node, ast.Name):
        # 不暴露 Python 全局；视为未定义 → None
        return None
    raise EJSEvalError(f"不允许的 AST 节点: {type(node).__name__}")


def _do_compare(left, op, right) -> bool:
    """带类型容错的比较：数字 vs 字符串数字会尽量转齐再比。"""
    if isinstance(op, (ast.Gt, ast.GtE, ast.Lt, ast.LtE)):
        # 尝试两侧转 float（处理 LLM 输出 "100" 这种字符串数字）
        try:
            l = float(left) if left is not None else float("-inf")
            r = float(right) if right is not None else float("-inf")
            if isinstance(op, ast.Gt): return l > r
            if isinstance(op, ast.GtE): return l >= r
            if isinstance(op, ast.Lt): return l < r
            if isinstance(op, ast.LtE): return l <= r
        except (TypeError, ValueError):
            return False
    if isinstance(op, ast.Eq):
        return left == right or str(left) == str(right)
    if isinstance(op, ast.NotEq):
        return not (left == right or str(left) == str(right))
    return False


def _truthy(v) -> bool:
    """JS 真值规则：None / False / 0 / "" / [] / {} → 假，其余真。"""
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)) and v == 0:
        return False
    if isinstance(v, (str, list, dict)) and len(v) == 0:
        return False
    return True


def _call_builtin(name: str, args: list, scope: dict):
    """处理白名单内的函数调用。"""
    if name in ("getvar", "getchatvar", "getMessageVar", "getMsgVar"):
        # 这几个在 ST 端语义不完全相同（chatvar 是 chat_metadata 整体），
        # v0 都映射到本地 scope 的点路径（最常见用法）。
        if not args:
            return None
        path = str(args[0])
        return _resolve_dot_path(scope, path)
    if name == "getglobalvar":
        # v0 没接全局桶。返回 None（与缺失统一）。
        return None
    # 其他函数视为 None（避免直接报错让用户卡住）
    return None


class EJSEvalError(Exception):
    pass


def _eval_expr(expr: str, scope: dict):
    """求值一个 EJS 表达式。失败返回 None 并 warning。"""
    if not expr or not expr.strip():
        return None
    try:
        py_expr = _translate_js_expr(expr)
        tree = ast.parse(py_expr, mode="eval")
        return _eval_ast(tree, scope)
    except Exception as e:
        logger.debug(f"EJS 求值失败 expr={expr!r} err={e}")
        return None


# ─── 渲染主循环（含 if 嵌套） ──────────────────────────────────────


def _render_tokens(
    tokens: list[tuple[str, str]], idx: int, scope: dict, stop_on: set[str]
) -> tuple[str, int]:
    """从 idx 开始渲染，直到遇到 stop_on 中的 token 或耗尽。

    返回 (rendered_string, next_idx_after_stop_token)。
    """
    out: list[str] = []
    i = idx
    n = len(tokens)
    while i < n:
        kind, payload = tokens[i]
        if kind in stop_on:
            return "".join(out), i
        if kind == _T_TEXT:
            out.append(payload)
            i += 1
            continue
        if kind == _T_EXPR:
            v = _eval_expr(payload, scope)
            out.append("" if v is None else str(v))
            i += 1
            continue
        if kind == _T_IF:
            cond = payload
            # 渲染 then 分支
            then_str, j = _render_tokens(tokens, i + 1, scope, {_T_ELSE, _T_ENDIF})
            else_str = ""
            if j < n and tokens[j][0] == _T_ELSE:
                else_str, j = _render_tokens(tokens, j + 1, scope, {_T_ENDIF})
            if j < n and tokens[j][0] == _T_ENDIF:
                j += 1
            cond_val = _eval_expr(cond, scope)
            if _truthy(cond_val):
                out.append(then_str)
            else:
                out.append(else_str)
            i = j
            continue
        if kind in (_T_ELSE, _T_ENDIF):
            # 孤立 ELSE/ENDIF（无匹配 IF）→ 跳过（不输出，避免污染 prompt）
            i += 1
            continue
        if kind == _T_RAW:
            # 不识别的 `<% ... %>` 块：v0 静默丢弃（不输出，不报错）
            # 理由：原样输出会让 LLM 看到 JS 噪音，比静默丢弃更糟。
            # 如果将来要支持更多语法，在 _classify_block 里识别即可。
            i += 1
            continue
        i += 1
    return "".join(out), i


# ─── 公开 API ──────────────────────────────────────────────────────


class EJSEngine:
    """EJS 极简引擎（线程安全：纯函数 + scope 只读）。"""

    @staticmethod
    def render(text: str, scope: dict | None = None) -> str:
        """求值并展开 text 里的 EJS 块。

        Args:
            text: 含 `<%_ %>` / `<%= %>` 的模板文本
            scope: MVU 变量上下文，形态 `{stat_data: {...}, ...}`
        """
        if not text or "<%" not in text:
            return text or ""
        if scope is None:
            scope = {}
        tokens = _tokenize(text)
        rendered, _ = _render_tokens(tokens, 0, scope, set())
        return rendered
