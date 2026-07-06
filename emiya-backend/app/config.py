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

    # === LLM 参数 — 记忆提取 ===
    MEMORY_EXTRACTION_TEMPERATURE: float = 0.3
    MEMORY_EXTRACTION_MAX_TOKENS: int = 500
    # Query 改写（检索前将口语化消息转为结构化查询）
    ENABLE_QUERY_REWRITING: bool = True

    # === ChromaDB 配置 ===
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    # Embedding 配置
    # "local" 默认尝试 BAAI/bge-large-zh-v1.5（需 pip install sentence-transformers）
    # 若 sentence-transformers 不可用则回退到 ChromaDB 内置 all-MiniLM-L6-v2
    EMBEDDING_PROVIDER: str = "local"
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
    # 好感度系统
    AFFINITY_MAX_DELTA: int = 3  # 单轮好感度最大变动幅度（±）

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

    # === 应用配置 ===
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

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
    # AN 默认深度（倒数第几条消息之前）
    WORLDBOOK_AN_DEFAULT_DEPTH: int = 4
    # AN 默认间隔（每 N 轮插一次，1 = 每次都插）
    WORLDBOOK_AN_DEFAULT_INTERVAL: int = 1
    # 尾部模板强制兜底：自动检测含 HTML 模板的激活条目，在 prompt 末端
    # 追加强制约束指令，压住预设的"严格格式"约束（如 <content></content>）
    # 详见 nodes.py::_detect_output_templates / _build_tail_template_directive
    WORLDBOOK_TAIL_TEMPLATE_ENFORCEMENT: bool = True
    # 尾部模板 prefix continuation 兜底：主回复扫缺失模板后用 DeepSeek prefix
    # completion 强制续写。详见 grilling 决策 Q1=A/Q2=β/Q3=α/Q4=α-1/Q5=K=3
    WORLDBOOK_TAIL_CONTINUATION_ENABLED: bool = True
    WORLDBOOK_TAIL_CONTINUATION_MAX: int = 3  # 每轮最多续写 K 个模板
    WORLDBOOK_TAIL_CONTINUATION_MAX_TOKENS: int = 800  # 单次续写 max_tokens

    # MVU 变量驱动世界书扫描白名单（ADR-0004，WuWa 档，**默认关闭**）：
    # 把选定的 stat_data 点路径渲染成扫描文本喂给世界书扫描器，让"带关键词的条目"
    # 能被当前变量激活（近似 ST 里 calculateStoryLogic 注入 should_scan 触发器的效果，
    # 但不执行任何卡内 JS，是尽力而为的替代）。空列表 = 关闭，不做任何额外扫描。
    # 也可按对话覆盖：conv.chat_config["mvu_scan_variable_paths"]。
    MVU_SCAN_VARIABLE_PATHS: list[str] = []

    # MVU double-ai update pass (ADR-0007): the main model writes narrative only,
    # then a second non-streaming tool call emits JSON Patch ops for stat_data.
    # Empty model means reuse DEEPSEEK_MODEL.
    MVU_UPDATE_MODEL: str | None = None
    MVU_UPDATE_TEMPERATURE: float = 0.2
    MVU_UPDATE_MAX_TOKENS: int = 1000
    MVU_UPDATE_FORCE_TOOL: bool = True

    # MVU tool-calling 更新通道（ADR-0005，**默认关闭**灰度）：开启后对 uses_mvu 卡
    # 在主调用里挂 update_variables 工具，单次返回 content + tool_call，post_process
    # 里过同一校验层写 stat_data。文本 <UpdateVariable> 解析永远作为 fallback 保留。
    MVU_TOOL_UPDATE_ENABLED: bool = False

    # MVU <UpdateVariable> 续写兜底（详见 ADR-0010）：
    # persona.uses_mvu=True 且主回复无 <UpdateVariable> 时，用 DeepSeek prefix
    # completion 强制续写状态变量 YAML 块。变量树可能很大，max_tokens 留 3000
    MVU_CONTINUATION_ENABLED: bool = True
    MVU_CONTINUATION_MAX_TOKENS: int = 3000

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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
