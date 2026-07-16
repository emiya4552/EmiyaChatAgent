/**
 * 用户可见配置的单一事实源（前端侧）。
 *
 * 与后端 `emiya-backend/app/services/config_registry.py` 平行——各为本栈权威。
 * 二者「对话覆盖层（chat_config）」的键 / 分组 / advanced / inheritable 必须一致，
 * 由 `configSchema.parity.test.ts` 对照后端 `tests/test_config_registry.py::EXPECTED_SCHEMA`
 * 快照保证。**改这里务必同步改后端 registry 与那份快照。**
 *
 * 两个正交维度（详见 docs/feat-adr 配置系统 ADR）：
 * - A｜功能分解（UI 骨架）：`group` 父分组 + `advanced` 是否高级子项（折叠默认收起）。
 * - B｜作用域继承（叶子解析）：`inheritable` 项在 chat_config 里 `null = 继承`；
 *   前端 select 用 'inherit' 作 UI 值，存库前经 helper 统一映射回 null。
 */

// ─── 维度 B：继承哨兵映射 helper（统一此前散写的三套写法）───

/** 可继承 enum：存储 string|null ↔ UI string（null → 'inherit'）。 */
export function enumFromInherit(v: string | null | undefined): string {
  return v ?? 'inherit'
}
export function enumToInherit(s: string): string | null {
  return s === 'inherit' ? null : s
}

/** 可继承布尔三态：存储 boolean|null ↔ UI 'yes'|'no'|'inherit'。 */
export function boolFromInherit(v: boolean | null | undefined): 'yes' | 'no' | 'inherit' {
  return v === true ? 'yes' : v === false ? 'no' : 'inherit'
}
export function boolToInherit(s: string): boolean | null {
  return s === 'yes' ? true : s === 'no' ? false : null
}

/** 可继承布尔三态的通用下拉选项（继承 / 开 / 关）。n-select :options 需可变数组，故不加 as const。 */
export const INHERIT_BOOL_OPTIONS = [
  { label: '继承', value: 'inherit' },
  { label: '开启', value: 'yes' },
  { label: '关闭', value: 'no' },
]

// ─── 维度 A：父分组元数据（label 前端持有，避免中英漂移）───

export interface ConfigGroup {
  id: string
  label: string
}

/** 分组 id 常量（与后端 config_registry.Group 的 id 对齐）。 */
export const GROUP = {
  SAMPLING: 'sampling',
  TOKEN_BUDGET: 'token_budget',
  WORLDBOOK: 'worldbook',
  OUTPUT_CONTRACT_EXEC: 'output_contract_exec',
  // 以下为账户 / 对话列层（不在后端 chat_config registry，前端独有分组）
  EMOTION: 'emotion',
  OUTPUT_CONTRACT_DETECT: 'output_contract_detect',
  MVU: 'mvu',
  DISPLAY: 'display',
  AUTHOR_NOTE: 'author_note',
  BINDINGS: 'bindings',
} as const

export const CONFIG_GROUPS: Record<string, ConfigGroup> = {
  [GROUP.SAMPLING]: { id: GROUP.SAMPLING, label: '采样参数' },
  [GROUP.TOKEN_BUDGET]: { id: GROUP.TOKEN_BUDGET, label: 'Token 预算' },
  [GROUP.WORLDBOOK]: { id: GROUP.WORLDBOOK, label: '世界书注入' },
  [GROUP.OUTPUT_CONTRACT_EXEC]: { id: GROUP.OUTPUT_CONTRACT_EXEC, label: '可见输出格式契约' },
  [GROUP.EMOTION]: { id: GROUP.EMOTION, label: '情感分析' },
  [GROUP.OUTPUT_CONTRACT_DETECT]: { id: GROUP.OUTPUT_CONTRACT_DETECT, label: '输出格式识别' },
  [GROUP.MVU]: { id: GROUP.MVU, label: 'MVU 兼容' },
  [GROUP.DISPLAY]: { id: GROUP.DISPLAY, label: '显示偏好' },
  [GROUP.AUTHOR_NOTE]: { id: GROUP.AUTHOR_NOTE, label: "Author's Note 作者笔记" },
  [GROUP.BINDINGS]: { id: GROUP.BINDINGS, label: '预设 / 模板 / 正则 / 世界书' },
}

// ─── chat_config 叶子元数据（镜像后端 EXPECTED_SCHEMA，19 项）───

export interface ChatConfigMeta {
  /** chat_config 键名（与 ChatConfig 字段同名）。 */
  key: string
  /** 父分组 id（维度 A）。 */
  group: string
  /** 是否高级子项：false=父级主控件常驻，true=折叠进高级区。 */
  advanced: boolean
  /** 是否可继承（维度 B）：true 时 null=继承账户默认/全局。 */
  inheritable: boolean
}

/**
 * 对话覆盖层（chat_config）全部合法键 + 分组/高级/继承。
 * **必须与后端 config_registry.CHAT_CONFIG_ITEMS 逐项一致**（见文件头）。
 */
export const CHAT_CONFIG_META: ChatConfigMeta[] = [
  // 采样（temperature 为主控件，其余高级）
  { key: 'temperature', group: GROUP.SAMPLING, advanced: false, inheritable: false },
  { key: 'top_p', group: GROUP.SAMPLING, advanced: true, inheritable: false },
  { key: 'top_k', group: GROUP.SAMPLING, advanced: true, inheritable: false },
  { key: 'top_a', group: GROUP.SAMPLING, advanced: true, inheritable: false },
  { key: 'min_p', group: GROUP.SAMPLING, advanced: true, inheritable: false },
  { key: 'frequency_penalty', group: GROUP.SAMPLING, advanced: true, inheritable: false },
  { key: 'presence_penalty', group: GROUP.SAMPLING, advanced: true, inheritable: false },
  { key: 'repetition_penalty', group: GROUP.SAMPLING, advanced: true, inheritable: false },
  // Token 预算（context 为主控件）
  { key: 'openai_max_context', group: GROUP.TOKEN_BUDGET, advanced: false, inheritable: false },
  { key: 'openai_max_tokens', group: GROUP.TOKEN_BUDGET, advanced: true, inheritable: false },
  { key: 'token_budget_safety_margin', group: GROUP.TOKEN_BUDGET, advanced: true, inheritable: false },
  { key: 'history_budget_cap', group: GROUP.TOKEN_BUDGET, advanced: true, inheritable: false },
  // 世界书注入
  { key: 'worldbook_budget_pct', group: GROUP.WORLDBOOK, advanced: true, inheritable: false },
  { key: 'worldbook_budget_cap', group: GROUP.WORLDBOOK, advanced: true, inheritable: false },
  { key: 'worldbook_overflow_alert', group: GROUP.WORLDBOOK, advanced: true, inheritable: false },
  // 可见输出契约·执行（全部 inheritable：null=继承账户默认/全局）
  { key: 'output_contract_mode', group: GROUP.OUTPUT_CONTRACT_EXEC, advanced: false, inheritable: true },
  { key: 'output_contract_allow_full_rewrite', group: GROUP.OUTPUT_CONTRACT_EXEC, advanced: true, inheritable: true },
  { key: 'output_contract_strict_fallback', group: GROUP.OUTPUT_CONTRACT_EXEC, advanced: true, inheritable: true },
  { key: 'output_contract_require_confirmed', group: GROUP.OUTPUT_CONTRACT_EXEC, advanced: true, inheritable: true },
]

/** 对照快照：{key: [group, advanced, inheritable]}，与后端 EXPECTED_SCHEMA 的前三项对齐。 */
export function chatConfigSnapshot(): Record<string, [string, boolean, boolean]> {
  const out: Record<string, [string, boolean, boolean]> = {}
  for (const m of CHAT_CONFIG_META) out[m.key] = [m.group, m.advanced, m.inheritable]
  return out
}

// ─── 账户级配置（User.account_config，ADR-4）───
// 数字旋钮的 min/max **必须与后端 config_registry.ACCOUNT_CONFIG_ITEMS 的 clamp 一致**。

import type { AccountConfig } from '../types'

/** AccountConfig 里值为 number 的键（派生，自动排除 bool/enum，随 AccountConfig 同步）。 */
export type NumericAccountKey = {
  [K in keyof AccountConfig]-?: NonNullable<AccountConfig[K]> extends number ? K : never
}[keyof AccountConfig]

export interface NumericKnob {
  key: NumericAccountKey
  label: string
  min: number
  max: number
  step: number
  /** 未设账户值时输入框占位提示（不写死全局默认，避免与后端 settings 漂移）。 */
  placeholder?: string
}

/** 记忆检索高级旋钮（B 桶，藏在“记忆系统 > 高级”折叠）。 */
export const MEMORY_ADVANCED_KNOBS: NumericKnob[] = [
  { key: 'memory_top_k', label: '检索条数 Top-K (条)', min: 1, max: 20, step: 1, placeholder: '跟随全局' },
  { key: 'memory_similarity_threshold', label: '相似度阈值 (0–1)', min: 0, max: 1, step: 0.05, placeholder: '跟随全局' },
  { key: 'memory_recency_weight', label: '时新权重 (0–1)', min: 0, max: 1, step: 0.05, placeholder: '跟随全局' },
  { key: 'memory_recency_half_life_days', label: '时新半衰期 (天)', min: 1, max: 3650, step: 1, placeholder: '跟随全局' },
  { key: 'memory_mmr_lambda', label: 'MMR λ (0–1，相关↔多样)', min: 0, max: 1, step: 0.05, placeholder: '跟随全局' },
  { key: 'memory_dedup_threshold', label: '去重阈值 (0–1)', min: 0, max: 1, step: 0.05, placeholder: '跟随全局' },
]

/** 上下文 / token 预算账户默认（“上下文 / Token 预算默认”段；预算键名同 chat_config）。 */
export const BUDGET_ACCOUNT_KNOBS: NumericKnob[] = [
  // 滑窗=保留多少条最近消息（消息计数）；上下文总上限=单轮请求总 token 天花板（input+输出共享）。
  { key: 'window_size', label: '滑窗大小 (条)', min: 4, max: 200, step: 1, placeholder: '跟随全局' },
  { key: 'openai_max_context', label: '上下文总上限 (tokens)', min: 1000, max: 2000000, step: 1000, placeholder: '跟随全局' },
  { key: 'token_budget_safety_margin', label: '安全余量 (tokens)', min: 0, max: 2000000, step: 500, placeholder: '跟随全局' },
  { key: 'history_budget_cap', label: '历史上限 (tokens，0=不限)', min: 0, max: 2000000, step: 1000, placeholder: '跟随全局' },
  { key: 'worldbook_budget_pct', label: '世界书预算 (%)', min: 0, max: 100, step: 1, placeholder: '跟随全局' },
  { key: 'worldbook_budget_cap', label: '世界书上限 (tokens，0=不限)', min: 0, max: 2000000, step: 1000, placeholder: '跟随全局' },
]

/** 记忆提取频率 3 档（→ 后端倍率 frequent=0.5 / standard=1 / sparse=2）。 */
export const EXTRACTION_CADENCE_OPTIONS = [
  { label: '密集', value: 'frequent' },
  { label: '标准', value: 'standard' },
  { label: '省 (稀疏)', value: 'sparse' },
]
