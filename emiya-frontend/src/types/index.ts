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
  // 大卡 raw_card 在后端 Redis 缓存的 key（TTL 10 min）
  // confirm 时通过 preview.card_data._cache_key 透传给后端取回完整数据
  cache_key: string | null
}

// ─── 用户 ───

export interface User {
  id: string
  email: string
  nickname: string
  avatar_url: string | null
  // 用户级 CSS 主题（详见 docs/adr/0008）
  css_theme: string | null
  created_at: string
}

export interface UserUpdateRequest {
  nickname?: string
  avatar_url?: string | null
  css_theme?: string | null
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
  // 世界书注入预算 % (config.WORLDBOOK_BUDGET_PCT 的对话级覆盖)
  worldbook_budget_pct?: number
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
  extras?: Record<string, any>
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
  type: 'static' | 'variable' | 'dynamic' | 'reply_length' | 'outlet' | 'author_note' | 'mes_example'
  label: string
  enabled: boolean
  role: 'system' | 'user' | 'assistant'
  content?: string | null
  variable_ref?: string | null
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
  created_at: string
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

export interface EmotionResult {
  emotion: string
  intensity: number
  confidence: number
  triggers: string[]
}

export interface EmotionRecord {
  id: string
  emotion: string
  intensity: number
  confidence: number
  triggers: string[]
  created_at: string
}

export interface MoodState {
  current_mood: string | null
  mood_intensity: number | null
}

// ─── 认证 ───

export interface LoginRequest { email: string; password: string }
export interface RegisterRequest { email: string; password: string; nickname: string }
export interface TokenResponse { access_token: string; token_type: string; user: User }
export interface MessageResponse { message: string }

// ─── 聊天 SSE ───

export interface ChatCallbacks {
  onToken: (content: string) => void
  onDone: (data: { message_id: string; conversation_id: string; new_memories?: number; affinity_score?: number }) => void
  onError: (error: string) => void
  onStop?: () => void
  onEmotion?: (emotion: EmotionResult) => void
  onMemoryRecall?: (memories: Array<{ content: string; relevance: number }>) => void
  onRelationshipChange?: (data: { level: number; level_name: string; affinity_score: number }) => void
  onMilestone?: (data: { key: string; name: string }) => void
  onProfileReminder?: (data: { message: string; link: string }) => void
  onAffinityUpdate?: (data: { delta: number; reason: string; score: number }) => void
  onWorldInfoActivated?: (data: WorldInfoActivated) => void
}

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

export interface Milestone { key: string; name: string; achieved_at?: string }
