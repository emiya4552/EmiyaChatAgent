# -*- coding: utf-8 -*-
"""用户可见配置的单一事实源（后端侧）。

本模块收敛「对话覆盖层」（`chat_config` JSONB）的键、系统默认与继承元数据，以及
可见输出契约执行模式的枚举/默认常量，取代此前散写的三处：

- `api/conversations.py::_system_default_chat_config`（系统默认回显）
- `output_contracts/policy.py` 里硬编码的 `DEFAULT_MODE` / `EXECUTION_MODES` 等
- `chat_config` 落库时缺失的白名单校验

**两个正交维度**（详见 `docs/feat-adr` 配置系统 ADR）：

- **A｜功能分解**（前端 UI 骨架）：`group` 父分组 + `advanced` 是否高级子项。
- **B｜作用域继承**（叶子解析）：`inheritable=True` 的项在 `chat_config` 里 `null=继承`
  账户默认 / 全局默认，resolve 顺序恒为「对话覆盖 > 账户默认 > 全局默认」。

前端 `emiya-frontend/src/config/configSchema.ts` 是与本文件平行的另一份权威（各管本栈），
两者的键 / 默认 / 分组以 `tests/test_config_registry.py` 的对照快照保证对齐——**改这里
务必同步改那里**。

范围约定：本次只收敛「已经用户可见」的配置。锁死在 `config.py` 的 `EMOTION_*` /
`MEMORY_*` / `SUMMARY_*` tuning 参数**不**在此登记、不新暴露（见 ADR「明确不做」）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings

# ── 可见输出契约执行模式（原 policy.py，集中到此供 policy 引用）──
EXECUTION_MODES: frozenset[str] = frozenset({"off", "auto", "guide", "repair", "strict"})
STRICT_FALLBACKS: frozenset[str] = frozenset({"repair", "guide", "off"})
DEFAULT_MODE = "auto"
DEFAULT_STRICT_FALLBACK = "repair"


# ── 父分组 id（前端据此渲染折叠区；label 由前端持有，避免中英漂移）──
class Group:
    SAMPLING = "sampling"
    TOKEN_BUDGET = "token_budget"
    WORLDBOOK = "worldbook"
    OUTPUT_CONTRACT_EXEC = "output_contract_exec"
    MEMORY = "memory"          # 账户级：记忆系统（ADR-4）
    CONTEXT = "context"        # 账户级：上下文/滑窗（ADR-4）


# 哨兵：区分"无系统默认"（不下发、由下游兜底）与"默认值恰好是 None"。
_UNSET: Any = object()


@dataclass(frozen=True)
class ChatConfigItem:
    """一个存于 `chat_config` JSONB 的对话覆盖配置项。

    key           `chat_config` 里的键名（与前端 ChatConfig 字段同名）。
    group         父分组 id（维度 A）。
    advanced      是否高级子项：False=父级主控件常驻，True=折叠进高级区。
    type          bool / int / float / enum / str，供前端选控件与校验。
    inheritable   True 时 `null=继承`（维度 B）；这类项不进 system_default。
    choices       enum 取值集合。
    default_setting  系统默认取自 `settings` 的哪个属性（运行时读，保持可配）。
    system_default   字面系统默认（与 default_setting 二选一）。

    「有系统默认」（default_setting 或 system_default 任一给出）的项才会进入
    `system_default_chat_config()`，用于前端「有效配置」回显；其余只作白名单成员。
    """

    key: str
    group: str
    advanced: bool
    type: str
    inheritable: bool = False
    choices: tuple[str, ...] | None = None
    default_setting: str | None = None
    system_default: Any = _UNSET

    @property
    def has_system_default(self) -> bool:
        return self.default_setting is not None or self.system_default is not _UNSET

    def resolve_default(self) -> Any:
        """运行时解析系统默认（default_setting 优先，实时读 settings）。"""
        if self.default_setting is not None:
            return getattr(settings, self.default_setting)
        return self.system_default


# 对话覆盖层（chat_config）全部合法键。顺序即前端建议渲染顺序。
CHAT_CONFIG_ITEMS: tuple[ChatConfigItem, ...] = (
    # ── 采样参数（temperature 为主控件，其余高级）──
    ChatConfigItem("temperature", Group.SAMPLING, False, "float",
                   default_setting="CHAT_TEMPERATURE"),
    ChatConfigItem("top_p", Group.SAMPLING, True, "float"),
    ChatConfigItem("top_k", Group.SAMPLING, True, "int"),
    ChatConfigItem("top_a", Group.SAMPLING, True, "float"),
    ChatConfigItem("min_p", Group.SAMPLING, True, "float"),
    ChatConfigItem("frequency_penalty", Group.SAMPLING, True, "float"),
    ChatConfigItem("presence_penalty", Group.SAMPLING, True, "float"),
    ChatConfigItem("repetition_penalty", Group.SAMPLING, True, "float"),
    # ── Token 预算（context 为主控件）──
    ChatConfigItem("openai_max_context", Group.TOKEN_BUDGET, False, "int",
                   default_setting="MAX_CONTEXT_TOKENS"),
    # 输出上限无稳定系统默认：未显式配置时由短/中/长回复长度决定，不进 effective 回显。
    ChatConfigItem("openai_max_tokens", Group.TOKEN_BUDGET, True, "int"),
    ChatConfigItem("token_budget_safety_margin", Group.TOKEN_BUDGET, True, "int",
                   default_setting="TOKEN_BUDGET_SAFETY_MARGIN"),
    ChatConfigItem("history_budget_cap", Group.TOKEN_BUDGET, True, "int",
                   system_default=0),
    # ── 世界书注入 ──
    ChatConfigItem("worldbook_budget_pct", Group.WORLDBOOK, True, "int",
                   default_setting="WORLDBOOK_BUDGET_PCT"),
    ChatConfigItem("worldbook_budget_cap", Group.WORLDBOOK, True, "int",
                   default_setting="WORLDBOOK_BUDGET_CAP"),
    # overflow_alert 合法但不进 effective 回显（保持既有行为：后端不主动下发默认）。
    ChatConfigItem("worldbook_overflow_alert", Group.WORLDBOOK, True, "bool"),
    # ── 可见输出契约·执行（全部 inheritable：null=继承账户默认/全局）──
    ChatConfigItem("output_contract_mode", Group.OUTPUT_CONTRACT_EXEC, False, "enum",
                   inheritable=True, choices=tuple(sorted(EXECUTION_MODES))),
    ChatConfigItem("output_contract_allow_full_rewrite", Group.OUTPUT_CONTRACT_EXEC, True,
                   "bool", inheritable=True),
    ChatConfigItem("output_contract_strict_fallback", Group.OUTPUT_CONTRACT_EXEC, True,
                   "enum", inheritable=True, choices=tuple(sorted(STRICT_FALLBACKS))),
    ChatConfigItem("output_contract_require_confirmed", Group.OUTPUT_CONTRACT_EXEC, True,
                   "bool", inheritable=True),
)

# key → item 索引（去重校验：键不得重复）。
_BY_KEY: dict[str, ChatConfigItem] = {}
for _it in CHAT_CONFIG_ITEMS:
    if _it.key in _BY_KEY:
        raise RuntimeError(f"config_registry: 重复的 chat_config 键 {_it.key!r}")
    _BY_KEY[_it.key] = _it


def get_chat_config_item(key: str) -> ChatConfigItem | None:
    return _BY_KEY.get(key)


def chat_config_allowed_keys() -> frozenset[str]:
    """`chat_config` 落库白名单：全部登记的对话覆盖键。"""
    return frozenset(_BY_KEY)


def system_default_chat_config() -> dict[str, Any]:
    """系统层面真正会下发的 chat_config 默认值（前端「有效配置」回显用）。

    只含「有系统默认」的项；像 top_p / top_k / 输出契约继承项不在此伪造默认。
    取代 `api/conversations.py::_system_default_chat_config`。
    """
    return {
        it.key: it.resolve_default()
        for it in CHAT_CONFIG_ITEMS
        if it.has_system_default
    }


def filter_chat_config(chat_config: dict | None) -> tuple[dict, list[str]]:
    """按白名单过滤 chat_config，返回（干净 dict, 被丢弃的未知键列表）。

    未知键不硬报错（兼容历史脏数据 / 前端新旧版本），由调用方决定是否 warning。
    """
    if not chat_config:
        return {}, []
    allowed = _BY_KEY
    clean: dict[str, Any] = {}
    dropped: list[str] = []
    for k, v in chat_config.items():
        if k in allowed:
            clean[k] = v
        else:
            dropped.append(k)
    return clean, dropped


# ═══════════════════════════════════════════════════════════════════════
# 账户级配置（User.account_config JSONB）——配置系统 ADR-4
# ═══════════════════════════════════════════════════════════════════════
# 放开此前锁死在 config.py 的记忆系统 tuning + 提供 token 预算账户默认层。
# 每项 account_config.get(key) 缺省回退全局 settings；越界值按 clamp 钳制。
# 记忆 tuning 与 token 预算键在**读取点**生效（见 nodes.py / chroma_client.py），
# 空 account_config = 全部继承全局，行为与 ADR-4 前完全一致。


@dataclass(frozen=True)
class MemoryTuning:
    """记忆检索/去重的有效调参（账户覆盖 → 全局回退，已钳制）。"""

    top_k: int
    threshold: float
    recency_weight: float
    recency_half_life_days: int
    mmr_lambda: float
    dedup_threshold: float


@dataclass(frozen=True)
class AccountConfigItem:
    """一个存于 `User.account_config` 的账户级配置项。

    default_setting  默认取自 `settings` 的哪个属性（运行时读，保持可配）。
    default          字面默认（与 default_setting 二选一，如 memory_enabled=True）。
    clamp            (min, max) 安全区间，防 footgun（如相似度阈值设 0.99 → 永远召回不到）。
    """

    key: str
    group: str
    advanced: bool
    type: str  # bool / int / float / enum
    default_setting: str | None = None
    default: Any = _UNSET
    clamp: tuple[float, float] | None = None
    choices: tuple[str, ...] | None = None

    def resolve_default(self) -> Any:
        if self.default_setting is not None:
            return getattr(settings, self.default_setting)
        return self.default

    def coerce(self, value: Any) -> Any:
        """把外部值收敛为本项类型 + 钳制；失败回退默认。"""
        try:
            if self.type == "bool":
                return bool(value)
            if self.type == "enum":
                return value if (self.choices and value in self.choices) else self.resolve_default()
            v: float = int(value) if self.type == "int" else float(value)
        except (TypeError, ValueError):
            return self.resolve_default()
        if self.clamp is not None:
            lo, hi = self.clamp
            v = max(lo, min(hi, v))
        return int(v) if self.type == "int" else v


# 提取频率 3 档 → 动态间隔倍率（越大越稀疏；乘在 nodes.py 的 dynamic_interval 上）。
EXTRACTION_CADENCE_MULTIPLIER = {"frequent": 0.5, "standard": 1.0, "sparse": 2.0}


ACCOUNT_CONFIG_ITEMS: tuple[AccountConfigItem, ...] = (
    # ── 记忆系统（memory_enabled 为父开关；其余高级）──
    AccountConfigItem("memory_enabled", Group.MEMORY, False, "bool", default=True),
    AccountConfigItem("memory_extraction_cadence", Group.MEMORY, True, "enum",
                      default="standard", choices=tuple(EXTRACTION_CADENCE_MULTIPLIER)),
    AccountConfigItem("memory_query_rewriting", Group.MEMORY, True, "bool",
                      default_setting="ENABLE_QUERY_REWRITING"),
    AccountConfigItem("memory_contradiction_detection", Group.MEMORY, True, "bool",
                      default_setting="ENABLE_CONTRADICTION_DETECTION"),
    AccountConfigItem("memory_top_k", Group.MEMORY, True, "int",
                      default_setting="MEMORY_TOP_K", clamp=(1, 20)),
    AccountConfigItem("memory_similarity_threshold", Group.MEMORY, True, "float",
                      default_setting="MEMORY_SIMILARITY_THRESHOLD", clamp=(0.0, 1.0)),
    AccountConfigItem("memory_recency_weight", Group.MEMORY, True, "float",
                      default_setting="RECENCY_WEIGHT", clamp=(0.0, 1.0)),
    AccountConfigItem("memory_recency_half_life_days", Group.MEMORY, True, "int",
                      default_setting="RECENCY_HALF_LIFE_DAYS", clamp=(1, 3650)),
    AccountConfigItem("memory_mmr_lambda", Group.MEMORY, True, "float",
                      default_setting="MMR_LAMBDA", clamp=(0.0, 1.0)),
    AccountConfigItem("memory_dedup_threshold", Group.MEMORY, True, "float",
                      default_setting="MEMORY_DEDUP_THRESHOLD", clamp=(0.0, 1.0)),
    # ── 上下文 ──
    AccountConfigItem("window_size", Group.CONTEXT, True, "int",
                      default_setting="WINDOW_SIZE", clamp=(4, 200)),
    # ── token 预算账户默认（键名与 chat_config 同名，读取点垫在对话覆盖之下）──
    AccountConfigItem("openai_max_context", Group.TOKEN_BUDGET, True, "int",
                      default_setting="MAX_CONTEXT_TOKENS", clamp=(1000, 2000000)),
    AccountConfigItem("token_budget_safety_margin", Group.TOKEN_BUDGET, True, "int",
                      default_setting="TOKEN_BUDGET_SAFETY_MARGIN", clamp=(0, 2000000)),
    AccountConfigItem("history_budget_cap", Group.TOKEN_BUDGET, True, "int",
                      default=0, clamp=(0, 2000000)),
    AccountConfigItem("worldbook_budget_pct", Group.WORLDBOOK, True, "int",
                      default_setting="WORLDBOOK_BUDGET_PCT", clamp=(0, 100)),
    AccountConfigItem("worldbook_budget_cap", Group.WORLDBOOK, True, "int",
                      default_setting="WORLDBOOK_BUDGET_CAP", clamp=(0, 2000000)),
)

_ACCOUNT_BY_KEY: dict[str, AccountConfigItem] = {}
for _ait in ACCOUNT_CONFIG_ITEMS:
    if _ait.key in _ACCOUNT_BY_KEY:
        raise RuntimeError(f"config_registry: 重复的 account_config 键 {_ait.key!r}")
    _ACCOUNT_BY_KEY[_ait.key] = _ait

# token 预算账户默认键（与 chat_config 同名）：account_budget_defaults 取子集垫底。
BUDGET_ACCOUNT_KEYS = frozenset(
    it.key for it in ACCOUNT_CONFIG_ITEMS if it.group in (Group.TOKEN_BUDGET, Group.WORLDBOOK)
)


def account_config_allowed_keys() -> frozenset[str]:
    return frozenset(_ACCOUNT_BY_KEY)


def account_value(account_config: dict | None, key: str) -> Any:
    """解析单个账户配置值：账户显式值（coerce+clamp）→ 全局默认。"""
    item = _ACCOUNT_BY_KEY[key]
    ac = account_config or {}
    if key in ac and ac[key] is not None:
        return item.coerce(ac[key])
    return item.resolve_default()


def memory_enabled(account_config: dict | None) -> bool:
    return bool(account_value(account_config, "memory_enabled"))


def query_rewriting_enabled(account_config: dict | None) -> bool:
    return bool(account_value(account_config, "memory_query_rewriting"))


def contradiction_detection_enabled(account_config: dict | None) -> bool:
    return bool(account_value(account_config, "memory_contradiction_detection"))


def resolve_window_size(account_config: dict | None) -> int:
    return int(account_value(account_config, "window_size"))


def resolve_extraction_multiplier(account_config: dict | None) -> float:
    return EXTRACTION_CADENCE_MULTIPLIER.get(
        account_value(account_config, "memory_extraction_cadence"), 1.0
    )


def account_budget_defaults(account_config: dict | None) -> dict[str, Any]:
    """账户显式设过的 token 预算默认（键名同 chat_config），供垫在对话覆盖之下。"""
    ac = account_config or {}
    return {
        k: account_value(ac, k)
        for k in BUDGET_ACCOUNT_KEYS
        if k in ac and ac[k] is not None
    }


def resolve_memory_tuning(account_config: dict | None) -> MemoryTuning:
    """空 account_config → 全部 settings 默认，与 ADR-4 前行为一致。"""
    return MemoryTuning(
        top_k=int(account_value(account_config, "memory_top_k")),
        threshold=float(account_value(account_config, "memory_similarity_threshold")),
        recency_weight=float(account_value(account_config, "memory_recency_weight")),
        recency_half_life_days=int(account_value(account_config, "memory_recency_half_life_days")),
        mmr_lambda=float(account_value(account_config, "memory_mmr_lambda")),
        dedup_threshold=float(account_value(account_config, "memory_dedup_threshold")),
    )


def filter_account_config(account_config: dict | None) -> tuple[dict, list[str]]:
    """按白名单过滤 + coerce/clamp。返回（干净 dict, 丢弃的未知键）。

    None 值视为「未设/回退全局」→ 不入库（保持 account_config 精简）。
    """
    if not account_config:
        return {}, []
    clean: dict[str, Any] = {}
    dropped: list[str] = []
    for k, v in account_config.items():
        item = _ACCOUNT_BY_KEY.get(k)
        if item is None:
            dropped.append(k)
        elif v is not None:
            clean[k] = item.coerce(v)
    return clean, dropped
