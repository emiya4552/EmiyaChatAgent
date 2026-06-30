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

    # === LLM 参数 — 情绪分析 ===
    EMOTION_TEMPERATURE: float = 0.1
    EMOTION_MAX_TOKENS: int = 150

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

    # MVU <UpdateVariable> 续写兜底（详见 ADR-0010）：
    # persona.uses_mvu=True 且主回复无 <UpdateVariable> 时，用 DeepSeek prefix
    # completion 强制续写状态变量 YAML 块。变量树可能很大，max_tokens 留 3000
    MVU_CONTINUATION_ENABLED: bool = True
    MVU_CONTINUATION_MAX_TOKENS: int = 3000

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
