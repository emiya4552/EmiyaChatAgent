# -*- coding: utf-8 -*-
"""MVU zod schema 初始默认值求值——**真跑 schema**（ADR-0021 延伸）。

MVU 卡用 zod schema 声明 stat_data 的结构 + 默认值（`.default`/`.prefault`/嵌套/
`preprocess`/`record`/`union`…）。自研的行正则解析器（`initialization._extract_static_schema_defaults`）
只认少数句式，撞到 `.prefault`（Zod v4）、`const Schema = z.object` 根写法、内嵌 preprocess/record
的 JS 就会漏字段 / 错嵌套——实测「魔法少女」卡的 `进程`/`系统状态` 脚手架整个丢失。

正解（与 ADR-0021 世界书 EJS 同一原则「不重写、直接跑」）：**在 V8 沙箱里加载真 zod v4 + 跑卡的
schema，调 `Schema.parse({})` 拿到完整、正确嵌套的默认 stat_data**。shim `registerMvuSchema` 捕获
Schema、`$` 立即执行 ready 回调、剥 import/export。schema 是**声明式定义**（无 I/O），跑在
mini-racer 沙箱里有界安全；不可用 / 无 schema / eval 或 parse 失败 → 返回 None，调用方回退行正则。

vendored `app/services/vendor/zod-global.js` 由 `esbuild zod@4 --bundle --format=iife`（全局 `z`）生成。
"""
from __future__ import annotations

import concurrent.futures
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# V8 访问（创建 + eval + call）全部收敛到这个单 worker 线程执行：worker 无事件循环 → mini-racer 的
# 阻塞 timeout 生效（schema 求值在 async 的 create_conversation 里，主线程直调带 timeout 的 call 会被拒），
# 且 MiniRacer isolate 与创建它的线程同线程使用（无跨线程隐患）。单 worker 天然序列化。
_v8_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="mvu-schema-v8")

try:  # mini-racer 是可选原生依赖；缺失则整条 V8 路径不可用，回退行正则。
    from py_mini_racer import MiniRacer, JSTimeoutException  # type: ignore

    _IMPORT_OK = True
except Exception as e:  # pragma: no cover
    MiniRacer = None  # type: ignore
    JSTimeoutException = Exception  # type: ignore
    _IMPORT_OK = False
    logger.info("[MVU schema] mini-racer 不可用，schema 默认值回退行正则: %s", e)

_VENDOR = Path(__file__).parent.parent / "vendor"
_ZOD = _VENDOR / "zod-global.js"
_LODASH = _VENDOR / "lodash.min.js"

# harness：捕获 registerMvuSchema 的参数；$ 立即执行 ready 回调（卡常把注册 gate 在 $(()=>…)）；
# toastr no-op 兜底。__mvu_extract_defaults(code)：eval schema → 取捕获的 Schema → parse({})。
_HARNESS = r"""
globalThis.__mvu_captured = null;
globalThis.registerMvuSchema = function (s) { globalThis.__mvu_captured = s; };
globalThis.$ = function (fn) {
  if (typeof fn === 'function') { try { fn(); } catch (e) {} }
  return { ready: function (f) { if (typeof f === 'function') { try { f(); } catch (e) {} } } };
};
globalThis.toastr = new Proxy({}, { get: function () { return function () {}; } });
function __mvu_extract_defaults(code) {
  globalThis.__mvu_captured = null;
  try {
    (0, eval)(code);
  } catch (e) {
    return { ok: false, err: 'eval: ' + String((e && e.message) || e) };
  }
  // 兼容两种 MVU 约定：registerMvuSchema(zodSchema)（根即 stat_data，如魔法少女）
  // 或 registerMvuSchema({ stat_data: zodSchema })（stat_data 包一层，如伶伶）。
  var s = globalThis.__mvu_captured;
  var schema = null;
  if (s && typeof s.parse === 'function') schema = s;
  else if (s && s.stat_data && typeof s.stat_data.parse === 'function') schema = s.stat_data;
  if (!schema) return { ok: false, err: 'no schema captured' };
  try {
    return { ok: true, data: schema.parse({}) };
  } catch (e) {
    return { ok: false, err: 'parse: ' + String((e && e.message) || e) };
  }
}
"""

# 剥静态 import + export 前缀（schema 只需这两项即可作为 classic 脚本 eval）。
_IMPORT_RE = re.compile(r"^[ \t]*import\s+(?!\()(?:[^;\n(]*?\s+from\s+)?['\"][^'\"]+['\"][ \t]*;?[ \t]*$", re.M)
_EXPORT_DEFAULT_RE = re.compile(r"^[ \t]*export\s+default\s+", re.M)
_EXPORT_DECL_RE = re.compile(r"^[ \t]*export\s+(?=(?:const|let|var|function|class|async)\b)", re.M)


def _strip_module_syntax(code: str) -> str:
    code = _IMPORT_RE.sub("", code)
    code = _EXPORT_DEFAULT_RE.sub("", code)
    code = _EXPORT_DECL_RE.sub("", code)
    return code


# V8 访问全部收敛到 worker 线程（`_v8_executor`）：MiniRacer 的创建 + eval + call 都在同一线程——避免
# 跨线程 V8 隐患，且 worker 无事件循环 → mini-racer 的阻塞 timeout 生效（schema 求值在 async 的
# create_conversation 里发生，主线程直调带 timeout 的 call 会被拒）。单 worker 天然序列化。
_ctx = None  # 仅 worker 线程内访问
_init_failed = False


def is_available() -> bool:
    return _IMPORT_OK and not _init_failed


def _worker_extract(code: str, timeout_ms: int):
    """worker 线程内：懒建 ctx（lodash + zod + harness）→ eval schema → parse({})。返回 {ok,...}。"""
    global _ctx
    if _ctx is None:
        ctx = MiniRacer()
        ctx.eval(_LODASH.read_text(encoding="utf-8"))  # 装 lodash（schema transform 可能用 _）
        ctx.eval(_ZOD.read_text(encoding="utf-8"))      # 装真 zod v4（全局 z）
        ctx.eval(_HARNESS)
        _ctx = ctx
        logger.info("[MVU schema] V8 沙箱 + zod 就位（真跑 schema 求默认值）")
    return _ctx.call("__mvu_extract_defaults", code, timeout=timeout_ms)


def _schema_scripts(scripts) -> list[str]:
    """挑出注册 schema 的脚本内容（同时含 registerMvuSchema 调用与 z.object 定义）。"""
    out: list[str] = []
    for s in scripts or []:
        content = str((s or {}).get("content") or "")
        if "registerMvuSchema" in content and "z.object" in content:
            out.append(content)
    return out


def extract_defaults(scripts, *, timeout_ms: int = 2000) -> dict | None:
    """在 V8 里真跑卡的 zod schema，返回 `Schema.parse({})` 的完整默认 stat_data。

    Args:
        scripts: 卡的 tavern_helper scripts（list[dict]，每个含 `content`）。
        timeout_ms: schema 求值超时（防病态 schema 卡死）。

    Returns:
        完整默认 stat_data（dict），或 None（不可用 / 无 schema / 失败 → 调用方回退行正则）。
    """
    global _init_failed
    if not _IMPORT_OK or _init_failed:
        return None
    schema_codes = _schema_scripts(scripts)
    if not schema_codes:
        return None
    code = _strip_module_syntax("\n;\n".join(schema_codes))
    try:
        res = _v8_executor.submit(_worker_extract, code, timeout_ms).result()
    except JSTimeoutException:
        logger.warning("[MVU schema] schema 求值超时，回退行正则")
        return None
    except Exception as e:  # pragma: no cover - 边界防御
        if _ctx is None:  # 上下文初始化失败（vendored 资源缺失等）→ 标记不可用
            _init_failed = True
        logger.warning("[MVU schema] schema 求值异常，回退行正则: %s", e)
        return None
    if isinstance(res, dict) and res.get("ok") and isinstance(res.get("data"), dict):
        return res["data"]
    if isinstance(res, dict):
        logger.info("[MVU schema] 未捕获 schema 默认值（回退行正则）: %s", res.get("err"))
    return None
