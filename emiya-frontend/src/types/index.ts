// ─── 角色卡 ───

export interface PersonaListItem {
  id: string
  name: string
  personality: string
  is_template: boolean
  is_owner: boolean
  tags: string[] | null
  avatar_url: string | null
  source: string
}

export interface MvuCompatibilityReport {
  is_mvu_card: boolean
  level: 'none' | 'supported' | 'partial'
  features: Record<string, number>
  supported: string[]
  unsupported: string[]
  details?: Array<{
    code: string
    status: 'supported' | 'unsupported' | 'warning'
    title: string
    summary: string
    detail: string
    count: number
    evidence: string[]
  }>
  warnings: string[]
}

export interface MvuConversationState {
  initialized: boolean
  stat_data_keys: string[]
  field_count: number
  initialized_at: string | null
  last_reload_at: string | null
  seeded_keys: string[]
  source_count: number
  warnings: string[]
}

export interface PersonaDetail {
  id: string
  user_id: string | null
  name: string
  personality: string
  background: string | null
  is_template: boolean
  first_message: string | null
  mes_example: string | null
  tags: string[] | null
  avatar_url: string | null
  card_data: Record<string, any> | null
  source: string
  source_url: string | null
  imported_at: string | null
  default_worldbook_ids: string[]
  // 角色卡内嵌 regex_scripts 拆出来的 RegexPreset ID（导入时自动挂；详见 ADR-0014）
  default_regex_preset_id: string | null
  author_note: string | null
  // v3 扩展（详见 docs/adr/0006）
  scenario: string | null
  alternate_greetings: string[]
  // 角色卡级 CSS 主题（详见 docs/adr/0008）
  css_theme: string | null
  // MVU 兼容标记（导入时自动判定，详见 docs/adr/0010）
  uses_mvu: boolean
  mvu_compatibility: MvuCompatibilityReport | null
  created_at: string
  updated_at: string | null
}

export interface PersonaCreateRequest {
  name: string
  personality: string
  background?: string | null
  first_message?: string | null
  mes_example?: string | null
  tags?: string[] | null
  avatar_url?: string | null
  scenario?: string | null
  alternate_greetings?: string[] | null
}

export interface PersonaUpdateRequest {
  name?: string
  personality?: string
  background?: string | null
  first_message?: string | null
  mes_example?: string | null
  tags?: string[] | null
  avatar_url?: string | null
  card_data?: Record<string, any> | null
  default_worldbook_ids?: string[]
  author_note?: string | null
  scenario?: string | null
  alternate_greetings?: string[] | null
  css_theme?: string | null
}

// ─── 导入/导出 ───

export interface ImportParseResult {
  source_format: string
  source_filename: string | null
  preview: Record<string, any>
  missing_fields: string[]
  duplicate_check: {
    is_duplicate: boolean
    similar_persona: { id: string; name: string } | null
  }
  avatar_preview: string | null
  mvu_compatibility?: MvuCompatibilityReport | null
  // 大卡 raw_card 在后端 Redis 缓存的 key（TTL 10 min）
  // confirm 时通过 preview.card_data._cache_key 透传给后端取回完整数据
  cache_key: string | null
}

// ─── 用户 ───

// 账户级配置桶（ADR-4）：记忆系统调参 + token 预算账户默认。所有键可选，
// 缺省=继承全局默认；键/默认/钳制的权威源见 config/configSchema.ts 与后端 config_registry。
export interface AccountConfig {
  // 记忆系统
  memory_enabled?: boolean
  memory_extraction_cadence?: 'frequent' | 'standard' | 'sparse'
  memory_query_rewriting?: boolean
  memory_contradiction_detection?: boolean
  memory_top_k?: number
  memory_similarity_threshold?: number
  memory_recency_weight?: number
  memory_recency_half_life_days?: number
  memory_mmr_lambda?: number
  memory_dedup_threshold?: number
  // 上下文
  window_size?: number
  // token 预算账户默认（键名与 chat_config 同名）
  openai_max_context?: number
  token_budget_safety_margin?: number
  history_budget_cap?: number
  worldbook_budget_pct?: number
  worldbook_budget_cap?: number
}

export interface User {
  id: string
  email: string
  nickname: string
  avatar_url: string | null
  // 用户级 CSS 主题（详见 docs/adr/0008）
  css_theme: string | null
  // 情感分析默认偏好：新建对话时 analyze_emotion 的初始值（详见 docs/adr/0020）
  default_analyze_emotion: boolean
  // MVU 兼容总开关：off 时聊天把 MVU 卡当普通卡（详见 docs/card/0002）
  mvu_compat_enabled: boolean
  // 世界书导入/编辑期是否自动调用 LLM 识别可见输出契约
  output_contract_llm_detection_enabled: boolean
  // 每次批量识别最多送检多少条候选世界书 entry
  output_contract_llm_detection_limit: number
  // 聊天期可见输出契约执行默认（ADR-1f）
  output_contract_default_mode: string
  output_contract_allow_full_rewrite: boolean
  output_contract_strict_fallback: string
  // 严格声明模式账户默认（ADR-2c）；null = 未表态，继承全局默认
  output_contract_require_confirmed: boolean | null
  // 账户级配置桶（ADR-4）：记忆系统调参 + token 预算账户默认
  account_config: AccountConfig
  created_at: string
}

export interface UserUpdateRequest {
  nickname?: string
  avatar_url?: string | null
  css_theme?: string | null
  default_analyze_emotion?: boolean
  mvu_compat_enabled?: boolean
  output_contract_llm_detection_enabled?: boolean
  output_contract_llm_detection_limit?: number
  output_contract_default_mode?: string
  output_contract_allow_full_rewrite?: boolean
  output_contract_strict_fallback?: string
  // null 显式发送 = 清空账户表态，回到继承全局默认
  output_contract_require_confirmed?: boolean | null
  // 账户级配置桶（ADR-4）：增量合并入现有 account_config；键值 null=清空该项回退全局
  account_config?: Partial<Record<keyof AccountConfig, number | boolean | string | null>>
}

export interface UserSession {
  id: string
  device_label: string
  ip_address: string | null
  created_at: string
  last_seen_at: string
  expires_at: string
  revoked_at: string | null
  is_current: boolean
  status: 'active' | 'revoked' | 'expired'
}

// ─── 对话 ───

export interface ChatConfig {
  temperature?: number
  top_p?: number
  top_k?: number
  top_a?: number
  min_p?: number
  frequency_penalty?: number
  presence_penalty?: number
  repetition_penalty?: number
  openai_max_tokens?: number
  openai_max_context?: number
  token_budget_safety_margin?: number
  history_budget_cap?: number
  // 世界书注入预算 % (config.WORLDBOOK_BUDGET_PCT 的对话级覆盖)
  worldbook_budget_pct?: number
  worldbook_budget_cap?: number
  worldbook_overflow_alert?: boolean
  // 可见输出契约聊天期执行覆盖（ADR-1f）；null/缺省 = 继承账户默认
  output_contract_mode?: string | null
  output_contract_allow_full_rewrite?: boolean | null
  output_contract_strict_fallback?: string | null
  // ADR-2c 严格声明模式覆盖；null/缺省 = 继承全局默认
  output_contract_require_confirmed?: boolean | null
}

export interface TokenBudgetReport {
  max_context: number
  reserved_output: number
  safety_margin: number
  prompt_prefix_tokens: number
  history_available: number
  history_cap: number
  history_budget: number
  reply_length: string
  history_tokens: number
  history_candidate_tokens: number
  history_dropped_tokens: number
  history_kept_messages: number
  history_candidate_messages: number
  final_prompt_tokens: number
  remaining_context: number
  worldbook: {
    budget: number
    used: number
    remaining: number
    pct: number
    cap: number
  }
}

export interface Conversation {
  id: string
  persona_id: string | null
  persona_name: string | null
  title: string | null
  user_persona_id: string | null
  user_persona_name: string | null
  preset_id: string | null
  preset_name: string | null
  chat_config: ChatConfig | null
  // 系统默认 ∪ chat_config，配置面板回显用
  effective_chat_config: ChatConfig | null
  template_id: string | null
  regex_preset_id: string | null
  // 世界书 + AN
  worldbook_ids: string[]
  author_note: string | null
  an_depth: number
  an_role: string
  an_interval: number
  // 情绪分析功能开关（无 template block；conv 级独立）
  analyze_emotion: boolean
  // 该 conv 有效模板里 reply_length block 是否启用——derived 字段（详见 ADR-0014）
  // false 时 ChatMain 右上的短/中/长按钮组应 disable
  reply_length_enabled: boolean
  // MVU 对话级变量桶（详见 ADR-0007）；只读暴露给前端展示
  variables: Record<string, unknown>
  mvu_state: MvuConversationState | null
  // MVU 卡界面危险能力 per-conversation 开关（ADR-0008d）；{ dangerous?: boolean }
  mvu_capabilities: Record<string, unknown>
  created_at: string
  updated_at: string
}

// ─── 世界书 ───

export interface WorldbookEntry {
  uid: number
  comment: string
  enabled: boolean
  content: string
  constant: boolean
  key: string[]
  keysecondary: string[]
  selective_logic: number   // 0=AND_ANY 1=NOT_ALL 2=NOT_ANY 3=AND_ALL
  scan_depth: number | null
  case_sensitive: boolean | null
  match_whole_words: boolean | null
  position: number          // 0..7
  depth: number
  order: number
  role: string              // system / user / assistant
  ignore_budget: boolean
  outlet_name: string | null
  output_contract?: OutputContractAttachment | null
  extras?: Record<string, any>
}

export interface OutputContractSectionDefinition {
  id: string
  label: string
  kind: string
  marker: string
  required: boolean
  order: number
  locator: Record<string, unknown>
  content_policy: Record<string, unknown>
  repair_policy: string
  capability: string
}

export interface OutputContractAttachment {
  schema_version: 2
  enabled: boolean
  definition: {
    document_kind: string
    placement: string
    once_per_reply: boolean
    sections: OutputContractSectionDefinition[]
    markers: string[]
    forbidden_terms: string[]
    render_profile: string
  }
  provenance: {
    source: string
    trigger: string
    confidence: number
    reason: string
    proposal?: { warnings?: string[] }
  }
  lifecycle: {
    content_hash: string
    detector_version: string
    reviewed: boolean
    status: 'active' | 'none' | 'unknown'
  }
  latest_auto_definition?: Record<string, unknown>
  latest_auto_provenance?: Record<string, unknown>
  is_stale?: boolean
}

export interface Worldbook {
  id: string
  user_id: string | null
  name: string
  description: string | null
  scan_depth: number
  case_sensitive: boolean
  match_whole_words: boolean
  entries: WorldbookEntry[]
  extensions: Record<string, any>
  created_at: string
  updated_at: string
}

export interface WorldbookListItem {
  id: string
  user_id: string | null
  name: string
  description: string | null
  entry_count: number
  is_template: boolean
  created_at: string
  updated_at: string
}

export interface WorldbookCreateRequest {
  name: string
  description?: string | null
  scan_depth?: number
  case_sensitive?: boolean
  match_whole_words?: boolean
  entries?: WorldbookEntry[]
  extensions?: Record<string, any>
}

export type WorldbookUpdateRequest = Partial<WorldbookCreateRequest>

export interface AuthorNoteUpdateRequest {
  author_note?: string | null
  an_depth?: number
  an_role?: string
  an_interval?: number
}

export interface WorldInfoActivated {
  entries: Array<{
    uid: number
    comment: string
    worldbook_id: string
    worldbook_name: string
    position: number
  }>
}

// ─── Prompt 模板 ───

export interface PromptBlock {
  id: string
  type: 'static' | 'dynamic' | 'reply_length' | 'outlet' | 'author_note' | 'mes_example'
  label: string
  enabled: boolean
  role: 'system' | 'user' | 'assistant'
  content?: string | null
  dynamic_ref?: string | null
  reply_length_config?: { short: string; medium: string; long: string } | null
  outlet_name?: string | null
}

export interface TemplateDetail {
  id: string
  name: string
  description: string | null
  is_default: boolean
  blocks: PromptBlock[]
  created_at: string
  updated_at: string | null
}

export interface TemplateListItem {
  id: string
  // user_id IS NULL 表示系统模板（全员可读、不可写不可删）；详见 ADR-0013
  user_id: string | null
  is_system: boolean
  name: string
  description: string | null
  is_default: boolean
  block_count: number
}

export interface TemplateCreateRequest {
  name: string
  description?: string | null
  blocks?: PromptBlock[]
  is_default?: boolean
}

export interface TemplateUpdateRequest {
  name?: string
  description?: string | null
  blocks?: PromptBlock[]
  is_default?: boolean
}

// ─── 预设 ───

export interface PromptEntry {
  identifier: string
  name: string
  role: string
  content: string
  enabled: boolean
  injection_position: number
  injection_depth: number
  injection_order: number
  system_prompt: boolean
  marker: boolean
  forbid_overrides: boolean
}

export interface PresetInfo {
  id: string
  name: string
  description: string | null
  prompt_count: number
  // 关联的正则预设 ID（用户创建对话时切预设可自动联动切正则；详见 ADR-0014）
  regex_preset_id: string | null
  created_at: string
  updated_at: string
}

export interface PresetDetail {
  id: string
  name: string
  description: string | null
  sampling_params: Record<string, any>
  context_settings: Record<string, any>
  prompts: PromptEntry[]
  extensions: Record<string, any>
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  // 显示版（ADR-0003 双管线）：markdownOnly 美化后的文本。为空/缺省时回退 content
  display_content?: string | null
  created_at: string
  // 可见输出契约本轮诊断（ADR-1e/1f）：随 message_done 到达，仅 assistant 消息可能有
  output_contract?: OutputContractDiag | null
}

// 可见输出契约本轮诊断稳定结构（ADR-1f）。三维分开：outcome=可检查规则是否满足、
// coverage=程序保证覆盖率、method=达成手段。initial/final 是两侧校验；guaranteed_rules
// 为程序保证的硬结构，soft_rules 只受 Prompt 引导。取代旧扁平结构（ADR-1c）。
export interface OutputContractSide {
  ok: boolean
  issues: Array<Record<string, unknown>>
}
export interface OutputContractDiag {
  contract_mode: string
  requested_mode?: string
  effective_mode?: string
  outcome: string // passed | failed | conflict | disabled
  coverage?: string // full | partial | none
  method?: string // initial | reconstructed | slot_completed | rewritten | strict_rendered | fallback
  initial?: OutputContractSide
  final?: OutputContractSide
  actions?: Array<Record<string, unknown>>
  guaranteed_rules?: string[]
  soft_rules?: string[]
  conflicts?: Array<Record<string, unknown>>
  latency_ms?: number
  extra_calls?: number
  token_usage?: number
}

// MVU 诊断运行时视图（ADR-0003 §3）：只读诊断，随 message_done 派生，不持久化
export interface MvuRuntimeViewEntry {
  role: 'update' | 'status' | 'plot' | 'initvar' | 'opening'
  role_label: string
  comment: string
  worldbook_id?: string | null
  worldbook_name?: string | null
  chars: number
  injected_as_prompt: boolean
}
// ADR-0005：本轮更新校验诊断
export interface MvuUpdateInfo {
  channel: 'tool' | 'text' | 'none'
  applied: number
  dropped: Array<{ path: string | null; reason: string }>
  coerced: Array<{ path: string; from: unknown; to: unknown }>
  clamped: Array<{ path: string; to: unknown }>
  meta?: {
    enabled_flag?: boolean
    persona_uses_mvu?: boolean
    tools_sent?: boolean
    tool_count?: number
    mvu_update_entries?: number
    tool_calls_received?: number
    tool_call_names?: string[]
  }
}
export interface MvuRuntimeView {
  is_mvu: boolean
  counts: Record<string, number>
  entries: MvuRuntimeViewEntry[]
  update?: MvuUpdateInfo
  diagnostics: string[]
}

// MVU 浏览器运行时 down-channel（ADR-0008c 阶段1）：message_done 在
// settings.MVU_BROWSER_RUNTIME 开时附带的一回合原料，喂给前端 MVU Host（薄 Mvu 层）
// 自己解析+应用+派生。off 时该字段不存在。
export interface MvuBrowserSync {
  base_stat: Record<string, any> // 应用前的 stat_data = S(N-1)
  raw_reply: string // 原始回复，含 inline <UpdateVariable>
  tool_calls: any[] // tool 通道的 update_variables 调用
  double_ai_ops?: any[] // double-ai 通道的 JSON Patch ops
}

// ─── 正则预设 ───

export interface RegexScript {
  id: string
  scriptName: string
  findRegex: string
  replaceString: string
  disabled: boolean
  promptOnly: boolean
  placement: number[]
}

export interface RegexPresetInfo {
  id: string
  name: string
  description: string | null
  script_count: number
  created_at: string
  updated_at: string
}

export interface RegexPresetDetail {
  id: string
  name: string
  description: string | null
  scripts: RegexScript[]
  created_at: string
  updated_at: string
}

// ─── 情绪 ───

export interface EmotionRecord {
  id: string
  emotion: string
  intensity: number
  confidence: number
  triggers: string[]
  created_at: string
}

// ─── 认证 ───

export interface LoginRequest { email: string; password: string }
export interface RegisterRequest { email: string; password: string; nickname: string }
export interface TokenResponse { access_token: string; token_type: string; user: User }
export interface MessageResponse { message: string }


// ─── 记忆 ───

export interface Memory {
  id: string
  content: string
  category: string
  importance: number
  reference_count: number
  scope: string
  memory_type: string
  source_conversation_id: string | null
  extracted_at: string
  last_referenced_at: string | null
}

export interface MemoryListResponse { items: Memory[]; total: number }
export interface MemoryUpdateRequest { content?: string; category?: string; scope?: string; memory_type?: string }

// ─── 情绪图表 ───

// 多对话模式：按日期聚合
export interface EmotionTrendPoint { date: string; dominant_emotion: string | null; avg_intensity: number }
// 单对话模式：按消息序号弧线（详见 docs/adr/0005）
export interface EmotionArcPoint {
  idx: number
  emotion: string
  intensity: number
  confidence: number
  triggers: string[]
  created_at: string | null
}
export interface EmotionDistributionItem { emotion: string; count: number; percentage: number }
export interface EmotionCalendarItem { date: string; dominant_emotion: string | null; avg_intensity: number | null }

// Dashboard filter 用
export interface EmotionScopePersona { id: string; name: string }
export interface EmotionScopeConversation { id: string; title: string; created_at: string | null }

// ─── 关系 ───

export interface Relationship {
  level: number
  level_name: string
  affinity_score: number
  total_messages: number
  deep_talk_count: number
  first_interaction: string | null
  last_interaction: string | null
  days_span: number
  milestones: string[]
  new_milestone?: string
  level_changed: boolean
}

