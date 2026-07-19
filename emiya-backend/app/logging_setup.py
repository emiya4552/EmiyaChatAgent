# -*- coding: utf-8 -*-
"""按类别把日志分流到不同文件 + 可选的控制台聚焦（不改任何业务 log 调用点）。

分类只**读**现有信息：logger 名 + 消息前缀 `[xxx]` + 少量关键词，一个字都不改
现有 log。一条 log 可同时属于多类（如契约的 prompt 锚定 `[整篇结构锚定]` 同属
prompt 与 contract），会写进多个文件。

两个控制旋钮：
1. 文件分流（始终生效）：logs/prompt.log、logs/output_contract.log、logs/app.log(兜底)。
   想看哪类就打开哪个文件。
2. 控制台聚焦（LOG_FOCUS）：all=全量（默认）/ prompt / contract。聚焦时控制台只留
   该类 + 通用，压下其它噪音；文件分流不受影响。

通用日志（无论开哪类都出现在每个类别文件、且聚焦时仍显示）判定：
- WARNING 及以上一律通用；
- logger 名属 COMMON_LOGGER_NAMES（如 uvicorn 的启动日志）；
- 消息带 COMMON_PREFIXES 前缀（如 `[核心]`）或含 COMMON_SUBSTRINGS 关键词。

────────────────────────────────────────────────────────────────────────
写 log 的标准（此前与以后都遵守；下面的表是唯一权威源）
- 提示词构成 → 用 PROMPT_PREFIXES 前缀开头。
- 输出契约   → 放在 `app.services.output_contracts` 包内即自动归类；包外补写契约
              log 用 CONTRACT_PREFIXES 前缀。
- MVU        → `mvu_runtime` 包 / `mvu_host` API 内自动归类；包外补写用 `[MVU...]` 前缀
              （前端 Host 日志在浏览器 Console，见 `mvu-log.mjs`，不经此分流）。
- 通用       → 用 `[核心]` 前缀；或 WARNING/ERROR 自动通用；无前缀的第三方/基础设施
              log 可把 logger 名加进 COMMON_LOGGER_NAMES 或关键词加进 COMMON_SUBSTRINGS。
- 未匹配任何类别的 log 不会丢，落 app.log 兜底。改表即可，无需动业务代码。
"""
from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

# ── 前缀 → 类别 标准表（唯一权威源）──────────────────────────────────
PROMPT_PREFIXES: tuple[str, ...] = (
    "[提示词注入]",
    "[整篇结构锚定]",   # 契约锚点注入，prompt / contract 重叠
    "[尾部模板兜底]",   # 契约锚点注入，prompt / contract 重叠
    "[WI]",
    "[WI Injector]",
    "[对话摘要]",
    "[新对话开始]",
)
CONTRACT_PREFIXES: tuple[str, ...] = (
    "[输出契约]",
    "[输出契约识别]",
    "[契约校验]",
    "[尾部模板续写]",
    "[整篇结构锚定]",   # 重叠
    "[尾部模板兜底]",   # 重叠
)
# logger 名以此开头的，整体归 contract（即使某条 log 没写前缀也归类）。
CONTRACT_LOGGER_PREFIX = "app.services.output_contracts"

# ── MVU（状态变量机 + 浏览器 Host 桥接）──────────────────────────────
# mvu_runtime 包 + mvu_host API 整体归 mvu；包外补写 MVU log 用 [MVU...] 前缀
# （[MVU-DOUBLE-AI] / [MVU-CAP] / [MVU_META_KEY] / [MVU-ADR5]… 均以 [MVU 开头，一网打尽）。
# 前端 MVU Host 日志在**浏览器 Console**（前缀 [MVU]，见 mvu-log.mjs），不经本后端分流。
MVU_PREFIXES: tuple[str, ...] = ("[MVU",)
MVU_LOGGER_PREFIXES: tuple[str, ...] = (
    "app.services.mvu_runtime",
    "app.api.mvu_host",
)

# ── 通用（common）判定：无论开哪类都要出现 ─────────────────────────
COMMON_PREFIXES: tuple[str, ...] = ("[核心]", "[COMMON]")
# 这些 logger（及其子 logger）的所有 record 视为通用，例如 uvicorn 启动/生命周期。
COMMON_LOGGER_NAMES: tuple[str, ...] = ("uvicorn",)
# 无前缀但属通用的关键 log，用消息子串匹配（脆弱，仅用于兜不到前缀的第三方/基础设施）。
COMMON_SUBSTRINGS: tuple[str, ...] = (
    "startup complete",           # uvicorn: Application startup complete.
    "Embedding 模型已加载",        # memory.chroma_client 启动加载
)
# 一律把 WARNING 及以上视为通用（错误/警告在任何调试视角都想看到）。
COMMON_MIN_LEVEL = logging.WARNING

# 类别 → 输出文件名。
CATEGORY_FILES: dict[str, str] = {
    "prompt": "prompt.log",
    "contract": "output_contract.log",
    "mvu": "mvu.log",
}
FOCUS_CHOICES = ("all", *CATEGORY_FILES.keys())


def _reset_log_files(log_dir: str) -> None:
    """删除本方案的日志文件（主文件 + rotation 备份），启动后由 handler 重建空文件。

    不能靠 RotatingFileHandler 的 mode='w'——它在 maxBytes>0 时会强制改回 'a'，
    截断无效。删文件失败（如被占用）时忽略，退化为追加，不影响启动。
    """
    for base in (*CATEGORY_FILES.values(), "app.log"):
        for p in Path(log_dir).glob(base + "*"):  # 主文件 + xxx.log.1/.2…
            try:
                p.unlink()
            except OSError:
                pass


def categories_of(record: logging.LogRecord) -> set[str]:
    """返回该 record 命中的类别集合（可为空/可多个）。"""
    cats: set[str] = set()
    msg = record.getMessage()
    if record.name.startswith(CONTRACT_LOGGER_PREFIX) or any(
        msg.startswith(p) for p in CONTRACT_PREFIXES
    ):
        cats.add("contract")
    if any(msg.startswith(p) for p in PROMPT_PREFIXES):
        cats.add("prompt")
    if record.name.startswith(MVU_LOGGER_PREFIXES) or any(
        msg.startswith(p) for p in MVU_PREFIXES
    ):
        cats.add("mvu")
    return cats


def is_common(record: logging.LogRecord) -> bool:
    if record.levelno >= COMMON_MIN_LEVEL:
        return True
    name = record.name
    if any(name == n or name.startswith(n + ".") for n in COMMON_LOGGER_NAMES):
        return True
    msg = record.getMessage()
    if any(msg.startswith(p) for p in COMMON_PREFIXES):
        return True
    return any(s in msg for s in COMMON_SUBSTRINGS)


class CategoryFilter(logging.Filter):
    """文件 handler 用：只放行目标类别（或通用）；target=None 放行全部（app.log 兜底）。"""

    def __init__(self, target: str | None):
        super().__init__()
        self.target = target

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if self.target is None:
            return True
        if is_common(record):
            return True
        return self.target in categories_of(record)


class FocusFilter(logging.Filter):
    """控制台 handler 用：focus=all 全量；否则只留该类 + 通用。"""

    def __init__(self, focus: str):
        super().__init__()
        self.focus = focus

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if self.focus == "all":
            return True
        if is_common(record):
            return True
        return self.focus in categories_of(record)


def setup_split_logging(
    *,
    log_dir: str = "logs",
    focus: str = "all",
    reset: bool = True,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    level: int = logging.INFO,
) -> None:
    """挂分类文件 handler（root + uvicorn），并按 focus 给控制台加聚焦过滤。

    reset=True（默认）时每次启动清空旧日志：主文件用 mode='w' 截断、删除 rotation
    备份，这样每次查看到的都只是本次运行的日志。reset=False 则追加累积。

    幂等：重复调用不重复挂载（热重载安全），reset 也只在首次挂载时执行。
    """
    focus = focus if focus in FOCUS_CHOICES else "all"
    root = logging.getLogger()
    if any(getattr(h, "_emiya_split", False) for h in root.handlers):
        return  # 已装过

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    if reset:
        _reset_log_files(log_dir)  # 删旧文件，handler 随后新建空文件
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    def _make(filename: str, target: str | None) -> logging.Handler:
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, filename),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setLevel(level)
        handler.setFormatter(fmt)
        handler.addFilter(CategoryFilter(target))
        handler._emiya_split = True  # type: ignore[attr-defined]
        return handler

    file_handlers = [_make(fn, cat) for cat, fn in CATEGORY_FILES.items()]
    file_handlers.append(_make("app.log", None))  # 全量兜底

    # 让 uvicorn 日志统一走 root：它默认自管 handler、不 propagate 到 root，
    # 那样启动/生命周期日志（Application startup complete 等）就进不了文件。清掉它
    # 自己的 handler 并打开 propagate，日志改由 root 统一出口（格式随项目统一）。
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    # 文件 handler 只挂 root，捕获所有 app.* 及 propagate 到 root 的记录（含 uvicorn）。
    for h in file_handlers:
        root.addHandler(h)

    # 控制台聚焦：给 root 现有的流式 handler（basicConfig 装的）加 FocusFilter。
    if focus != "all":
        focus_filter = FocusFilter(focus)
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(
                h, logging.FileHandler
            ):
                h.addFilter(focus_filter)
