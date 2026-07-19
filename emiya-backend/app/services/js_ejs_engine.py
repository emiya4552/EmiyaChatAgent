# -*- coding: utf-8 -*-
"""世界书 EJS 的**真 JS 沙箱**求值引擎（ADR-0021）。

背景：MVU 重逻辑卡（如「魔法少女」）把整套游戏引擎写进世界书条目里，用 EJS `<% %>`
调**真 JS + lodash** 读 `stat_data` 动态裁剪 prompt：`_.get(...)`、箭头函数、`.includes()`、
`.filter()`、`Object.keys()`、`Math.*`、`_.random/_.sampleSize` 等。自研的 `ejs_engine.py`
（v0，ADR-0010）只支持 `getvar('点.路径')` + 干净的单块 `<% if(){ %>`，撞到这类写法会**静默出错**
（把 `if(){...}` 当普通 EXEC 丢弃 → 状态门失效 → 互斥分支同时泄漏进 prompt）。

方案 B（真 JS 沙箱）：用 V8（mini-racer）加载真 lodash + 一个极简 EJS 编译器，把卡的 EJS 模板
编译成 JS 函数原生执行。经实测这张卡 48 条世界书里 43/44 条 EJS 干净渲染、状态门正确生效
（善良态渲染善良人格、堕落态为空——正是 v0 泄漏的那条）。

安全：V8 isolate 默认沙箱——无 fs / 网络 / require / process；每次渲染带 `timeout`（防死循环）。
只读：世界书 EJS 不写变量（实测该卡无 `setvar`），`setvar/setglobalvar` 装成 no-op。

回退：mini-racer 不可用（未装 / 初始化失败）或单条渲染抛错 / 超时 → 由 `render_with_fallback`
回退到 v0 `EJSEngine`（绝不比现状更差）。用 `MVU_JS_EJS_ENABLED` 开关整体启停。

作用域对齐 v0：`getvar(path)` = 在 scope 上做点路径取值（`getvar('stat_data')` → scope.stat_data）；
`getwi(a,b)` = scope.__wi_entries 查表。scope 形态即 injector 传入的 `ejs_scope`
（`{stat_data, __wi_entries, ...}`），与 v0 `EJSEngine.render` 同一个入参，两条路径可无缝互换。
"""
from __future__ import annotations

import concurrent.futures
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# V8 访问（创建 + eval + call）全部收敛到这个单 worker 线程：worker 无事件循环 → mini-racer 的阻塞
# timeout 生效（世界书 EJS 求值在 async 的 node_build_prompt 里，主线程直调带 timeout 的 call 会被拒 →
# 每次回退 v0，V8 形同虚设），且 MiniRacer isolate 同线程使用（无跨线程隐患）。单 worker 天然序列化，
# 外层阻塞等结果——与既有同步 CPU prompt 构建（v0 EJSEngine / MacroEngine）同性质。
_v8_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="mvu-ejs-v8")

try:  # mini-racer 是可选原生依赖：装不上则整条 V8 路径不可用，回退 v0。
    from py_mini_racer import MiniRacer, JSTimeoutException  # type: ignore

    _IMPORT_OK = True
except Exception as e:  # pragma: no cover - 取决于部署环境
    MiniRacer = None  # type: ignore
    JSTimeoutException = Exception  # type: ignore
    _IMPORT_OK = False
    logger.info("[MVU EJS] mini-racer 不可用，世界书 EJS 将回退 v0 引擎: %s", e)

_VENDOR_LODASH = Path(__file__).parent / "vendor" / "lodash.min.js"

# ── JS 侧：EJS 编译器 + 渲染 harness（在 V8 里一次性装好）──────────────
# __compileEjs：把 EJS 模板编译成一段"push 文本 / push 表达式 / 内联代码"的 JS 函数体。
#   - `<%# %>` 注释；`<%= %>` / `<%- %>` 表达式（原样输出，prompt 文本不做 HTML 转义）；
#   - `<% %>` / `<%_ %>` 内联代码（控制流、箭头函数、lodash 等，V8 原生跑）；
#   - 空白吞并：`<%_` 吞掉标签前的行内空白，`_%>` / `-%>` 吞掉标签后的换行（减少 prompt 空行噪音）。
# renderEjs：装 getvar/getwi/_ 作用域后 `new Function` 执行编译体，返回 {ok,out} | {ok:false,err}。
_HARNESS = r"""
function __compileEjs(tpl){
  var code = ["var __out=[];"];
  var re = /<%(_|=|-|#)?([\s\S]*?)(_|-)?%>/g;
  var last = 0, m, stripLead = false;
  function emitText(t){
    if(stripLead){ t = t.replace(/^[ \t]*\r?\n/, ""); stripLead = false; }
    if(t) code.push("__out.push(" + JSON.stringify(t) + ");");
  }
  while((m = re.exec(tpl))){
    var text = tpl.slice(last, m.index);
    var pfx = m[1], bdy = m[2], sfx = m[3];
    if(pfx === "_"){ text = text.replace(/[ \t]*$/, ""); }
    emitText(text);
    if(pfx === "#"){ /* comment */ }
    else if(pfx === "=" || pfx === "-"){ code.push("__out.push(String((" + bdy + ") ?? ''));"); }
    else { code.push(bdy); }
    if(sfx === "_" || sfx === "-"){ stripLead = true; }
    last = re.lastIndex;
  }
  emitText(tpl.slice(last));
  code.push("return __out.join('');");
  return code.join("\n");
}
function renderEjs(tpl, scope){
  scope = scope || {};
  var wi = scope.__wi_entries || {};
  function getvar(path){ if(path == null) return undefined; return _.get(scope, String(path)); }
  function getchatvar(path){ return getvar(path); }
  function setvar(){ return undefined; }        // 世界书 EJS 只读，写变量 no-op
  function setglobalvar(){ return undefined; }
  function getglobalvar(){ return undefined; }  // v0 未接全局桶，统一 undefined
  function getwi(a, b){ var k = (b == null ? a : b); return (wi && wi[k] != null) ? wi[k] : ""; }
  try {
    var fn = new Function(
      "_", "getvar", "getchatvar", "setvar", "setglobalvar", "getglobalvar", "getwi", "scope", "variables",
      __compileEjs(tpl)
    );
    var out = fn(_, getvar, getchatvar, setvar, setglobalvar, getglobalvar, getwi, scope, scope);
    return { ok: true, out: (out == null ? "" : String(out)) };
  } catch (e) {
    return { ok: false, err: (e && e.message) ? e.message : String(e) };
  }
}
"""


class JsEjsUnavailable(Exception):
    """V8 路径不可用（mini-racer 未装 / 上下文初始化失败）→ 调用方应回退 v0。"""


class JsEjsRenderError(Exception):
    """单条模板在 V8 里渲染抛错 / 超时 → 调用方应回退 v0。"""


# V8 访问全部收敛到**单 worker 线程**（`_v8_executor`）：MiniRacer 的创建 + eval + call 都在同一线程，
# 主线程只 submit + result。这样 ① 无跨线程 V8 隐患（isolate 绑定创建它的线程）；② worker 线程无事件
# 循环 → mini-racer 的阻塞 timeout 生效（在 async 的 node_build_prompt 里直接调带 timeout 的 call 会被拒，
# 从而每次回退 v0——那是 bug）；③ 单 worker 天然序列化，无需额外锁。
_ctx = None  # 仅在 worker 线程内访问
_init_failed = False


def is_available() -> bool:
    """V8 路径当前是否可用（mini-racer 可导入且上下文未初始化失败）。"""
    return _IMPORT_OK and not _init_failed


def _worker_render(template: str, scope: dict, timeout_ms: int):
    """在 worker 线程内执行：懒建 ctx（首次装 lodash + harness）→ 渲染。返回 renderEjs 的 {ok,...}。"""
    global _ctx, _init_failed
    if _ctx is None:
        ctx = MiniRacer()
        ctx.eval(_VENDOR_LODASH.read_text(encoding="utf-8"))  # 装真 lodash（_）
        ctx.eval(_HARNESS)  # 装 EJS 编译器 + renderEjs
        _ctx = ctx
        logger.info("[MVU EJS] V8 沙箱 + lodash 就位（世界书 EJS 走真 JS 求值）")
    return _ctx.call("renderEjs", template, scope, timeout=timeout_ms)


def render(template: str, scope: dict | None = None, timeout_ms: int = 300) -> str:
    """在 V8 沙箱里求值一段 EJS 模板。

    Args:
        template: 含 `<% %>` 的世界书条目内容。
        scope: 变量作用域（injector 的 ejs_scope，形如 `{stat_data, __wi_entries, ...}`）。
        timeout_ms: 单条渲染超时（防卡内死循环）。

    Returns:
        渲染后的字符串。

    Raises:
        JsEjsUnavailable: V8 路径不可用。
        JsEjsRenderError: 渲染抛错 / 超时（调用方应回退 v0）。
    """
    global _init_failed
    if not template or "<%" not in template:
        return template or ""
    if not _IMPORT_OK or _init_failed:
        raise JsEjsUnavailable("mini-racer 不可用")
    scope = scope or {}
    try:
        res = _v8_executor.submit(_worker_render, template, scope, timeout_ms).result()
    except JSTimeoutException as e:
        raise JsEjsRenderError(f"timeout: {e}")
    except Exception as e:
        # 上下文初始化失败（如 vendored 资源缺失）→ 标记不可用，后续直接回退，别每条都试。
        if _ctx is None:
            _init_failed = True
            logger.warning("[MVU EJS] V8 上下文初始化失败，回退 v0: %s", e)
            raise JsEjsUnavailable(str(e))
        raise JsEjsRenderError(str(e))
    if isinstance(res, dict):
        if res.get("ok"):
            return res.get("out") or ""
        raise JsEjsRenderError(str(res.get("err") or "render failed"))
    raise JsEjsRenderError(f"unexpected result shape: {type(res).__name__}")


def render_with_fallback(template: str, scope: dict | None, *, enabled: bool) -> str:
    """世界书 EJS 求值分发：V8 优先，**任何不可用 / 出错都回退 v0 `EJSEngine`**（不regress）。

    `enabled` = `settings.MVU_JS_EJS_ENABLED`（整体开关）。
    """
    if enabled and is_available():
        try:
            return render(template, scope)
        except (JsEjsUnavailable, JsEjsRenderError) as e:
            logger.debug("[MVU EJS] V8 渲染失败，回退 v0: %s", e)
    from app.services.ejs_engine import EJSEngine

    return EJSEngine.render(template, scope or {})
