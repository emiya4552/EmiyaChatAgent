# -*- coding: utf-8 -*-
"""应用配置模块，从环境变量加载所有配置项。"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，从 .env 文件和环境变量加载。"""

    # === DeepSeek API 配置 ===
    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1" 
    DEEPSEEK_MODEL: str         
    DEEPSEEK_TIMEOUT: float = 60.0

    # === 上下文管理 ===
    WINDOW_SIZE: int = 40  # 滑动窗口大小：最近 N 条消息（20 轮）
    MAX_CONTEXT_TOKENS: int = 80000  # 上下文 token 上限（DeepSeek 80%）

    # === LLM 参数 — 聊天 ===
    CHAT_TEMPERATURE: float = 0.7
    # 默认输出 token 上限（chat_config.openai_max_tokens 缺省时回退到此）。
    # 超出由 LLM 端强制截断。
    CHAT_MAX_TOKENS: int = 20000

    # === LLM 参数 — 情感感知（情绪+好感度合并调用，ADR-0019） ===
    EMOTION_TEMPERATURE: float = 0.1
    # assess_turn 的输入按 token 预算裁剪（而非固定字符截断），避免长 RP 消息被一刀切；
    # 近期对话从最新往回累加，最新消息优先。
    EMOTION_ASSESS_MAX_TOKENS: int = 250       # 输出 JSON 上限
    EMOTION_CONTEXT_MAX_TOKENS: int = 10000      # 近期对话输入预算（token，最新优先累加）
    EMOTION_CONTEXT_MAX_MESSAGES: int = 12     # 近期对话最多带几条（防呆上限，token 预算才是主控）
    EMOTION_REPLY_MAX_TOKENS: int = 1000        # AI 回复输入预算（好感度关键输入，给厚一点）
    EMOTION_PERSONA_MAX_TOKENS: int = 1000      # 人设 + 场景输入预算（可为空——高版本卡人设在世界书里）
    # 用户消息去空白后短于此长度 → 跳过整次感知调用（省 token/去噪；"嗯""哦"这类填充轮）。
    # 注意中文很"密"：3-4 字常已很有情绪（"我爱你"/"对不起"/"我好累"），阈值设 2 表示只跳
    # 单字/空消息，是保守安全值；调高会误伤有意义的短消息，慎调。
    EMOTION_SKIP_TRIVIAL_CHARS: int = 2

    # === LLM 参数 — 摘要压缩 ===
    SUMMARY_TEMPERATURE: float = 0.3
    SUMMARY_MAX_TOKENS: int = 500
    SUMMARY_BATCH_MESSAGES: int = 10  # 累计多少条新溢出消息后触发一次后台摘要

    # === LLM 参数 — 记忆提取 ===
    MEMORY_EXTRACTION_TEMPERATURE: float = 0.3
    MEMORY_EXTRACTION_MAX_TOKENS: int = 500
    # Query 改写（检索前将口语化消息转为结构化查询）
    ENABLE_QUERY_REWRITING: bool = True

    # === ChromaDB 配置 ===
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    # Embedding 配置
    # 默认尝试 BAAI/bge-large-zh-v1.5（需 pip install sentence-transformers）；
    # 不可用则回退到 ChromaDB 内置 all-MiniLM-L6-v2
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-large-zh-v1.5"
    # 记忆系统配置
    MEMORY_TOP_K: int = 5
    MEMORY_SIMILARITY_THRESHOLD: float = 0.5
    MEMORY_MAX_PER_USER: int = 200  # 每用户最大记忆条数
    # 渐进式提取：记忆少时密集采集，记忆多时降低频率
    MEMORY_EXTRACTION_AGGRESSIVE: int = 2   # 记忆 < 10 条时，每 N 轮提取
    MEMORY_EXTRACTION_MODERATE: int = 5     # 记忆 10-30 条时
    MEMORY_EXTRACTION_SPARSE: int = 8       # 记忆 > 30 条时
    MEMORY_EXTRACTION_DELAY: float = 0   # 后台提取任务延迟秒数（0=不延迟）
    # 记忆衰减：combined_score = (1 - RECENCY_WEIGHT) × similarity + RECENCY_WEIGHT × recency
    RECENCY_WEIGHT: float = 0.3 
    RECENCY_HALF_LIFE_DAYS: int = 30  # 30 天后 recency 权重衰减到 0.5
    # MMR 多样性：lambda=1 纯相似度，lambda=0 纯多样性
    MMR_LAMBDA: float = 0.7
    # 去重与矛盾检测
    MEMORY_DEDUP_THRESHOLD: float = 0.75  # 相似度 ≥ 此值视为重复（原 0.85，放宽以提高提取量）
    ENABLE_CONTRADICTION_DETECTION: bool = True

    # === 数据库配置 ===
    DATABASE_URL: str

    # === Redis 配置 ===
    REDIS_URL: str = "redis://localhost:6379/0"

    # === JWT 配置 ===
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # === Email / SMTP 配置 ===
    FRONTEND_BASE_URL: str = "http://localhost:5173"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_FROM_NAME: str = "EMIYA"
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    # === Token Budget 配置 ===
    # token 预算安全边界，覆盖计数误差
    TOKEN_BUDGET_SAFETY_MARGIN: int = 2000

    # === Worldbook 配置 ===
    # 全局扫描深度默认（取最近 N 条消息组成扫描缓冲区）
    WORLDBOOK_DEFAULT_SCAN_DEPTH: int = 2
    # 单次扫描中世界书内容允许占 max_context 的百分比
    WORLDBOOK_BUDGET_PCT: int = 25
    # 绝对 token 上限，0 = 无上限
    WORLDBOOK_BUDGET_CAP: int = 0
    # 预算超限时是否日志告警（前端目前不展示）
    WORLDBOOK_OVERFLOW_ALERT: bool = False
    # 尾部模板强制兜底：自动检测含 HTML 模板的激活条目，在 prompt 末端
    # 追加强制约束指令，压住预设的"严格格式"约束（如 <content></content>）
    # 详见 output_contracts.tail 的 detect/build directive 逻辑
    WORLDBOOK_TAIL_TEMPLATE_ENFORCEMENT: bool = True
    # 尾部模板 prefix continuation 兜底：主回复扫缺失模板后用 DeepSeek prefix
    # completion 强制续写。实现集中在 output_contracts.tail。
    WORLDBOOK_TAIL_CONTINUATION_ENABLED: bool = True
    WORLDBOOK_TAIL_CONTINUATION_MAX: int = 3  # 每轮最多续写 K 个模板
    WORLDBOOK_TAIL_CONTINUATION_MAX_TOKENS: int = 800  # 单次续写 max_tokens

    # 可见输出契约「严格声明模式」（ADR-2c，**默认关**）：on 时聊天运行时只**执行**
    # 已确认 / 声明的契约（reviewed=true 或 source=manual），未确认的自动识别草稿降为
    # 仅 Prompt 引导（仍锚定，不做校验后修复 / 续写 / strict）。默认关＝草稿照旧生效、
    # 开箱即用。也可由对话 chat_config.output_contract_require_confirmed 覆盖。
    OUTPUT_CONTRACT_REQUIRE_CONFIRMED: bool = False

    # MVU double-ai update pass (ADR-0007): the main model writes narrative only,
    # then a second non-streaming tool call emits JSON Patch ops for stat_data.
    # Empty model means reuse DEEPSEEK_MODEL.
    MVU_UPDATE_MODEL: str | None = None
    MVU_UPDATE_TEMPERATURE: float = 0.2
    MVU_UPDATE_MAX_TOKENS: int = 1000
    MVU_UPDATE_FORCE_TOOL: bool = True

    # MVU 浏览器运行时 down-channel（ADR-0008c 阶段1，**默认关闭**）：
    # 开启后，对 uses_mvu 卡在 message_done 里**附加** mvu_browser_sync = 本回合层1
    # 的原料（应用前的 base stat_data + 原始回复 raw_reply + tool_calls），供前端
    # MVU Host（ADR-0008b 薄 Mvu 层）自己解析+应用+派生。
    # 阶段1 是纯附加：后端仍照旧解析+应用写 conv.variables，不改现有行为。等前端运行时
    # 上线并回传结算态（State Sync UP 通道）后，再在后续阶段据此关掉后端 apply。
    MVU_BROWSER_RUNTIME: bool = False

    # MVU 退役后端 apply（ADR-0008c 阶段3，**默认关闭**）：
    # on 且 MVU_BROWSER_RUNTIME on 且 uses_mvu 时，node_post_process **不再**把 ops 应用到
    # conv.variables —— ops 随 mvu_browser_sync 下推，由前端 MVU Host 应用+派生并经
    # PUT /mvu-state UP 回传持久化。浏览器成为 MVU 状态唯一权威。
    # 默认关：后端照旧 apply（前端 UP 覆盖），保住无浏览器/关页时的兜底。前端运行时稳后再开。
    MVU_RETIRE_BACKEND_APPLY: bool = False

    # === 日志分文件（app/logging_setup.py）===
    # 按类别把业务日志分流到 LOG_DIR 下不同文件（prompt.log / output_contract.log /
    # app.log 兜底）。只读现有 logger 名 + 消息前缀，不改任何业务 log；控制台照旧全量。
    LOG_SPLIT_ENABLED: bool = True
    LOG_DIR: str = "logs"
    # 控制台聚焦：all=全量（默认）/ prompt / contract。聚焦时控制台只留该类 + 通用，
    # 压下其它噪音；文件分流（prompt.log / output_contract.log / app.log）始终不受影响。
    LOG_FOCUS: str = "all"
    # 每次启动清空旧日志（截断主文件 + 删 rotation 备份），便于每次只看本次运行；
    # 设 false 则跨运行追加累积。
    LOG_RESET_ON_START: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
