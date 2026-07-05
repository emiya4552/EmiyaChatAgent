import api from './index'
import type { Conversation, ChatConfig, RegexScript } from '../types'

export async function fetchConversations(): Promise<Conversation[]> {
  const res = await api.get('/v1/conversations')
  return res.data
}

export interface CreateConversationOptions {
  userPersonaId?: string
  title?: string
  presetId?: string
  templateId?: string
  /** 显式选择的正则预设；不传则后端按 preset > persona 兜底 */
  regexPresetId?: string
  /** 显式绑定的世界书；undefined 时后端用 persona.default_worldbook_ids 兜底 */
  worldbookIds?: string[]
  greetingIndex?: number
}

export async function createConversation(
  personaId: string,
  options: CreateConversationOptions = {},
): Promise<Conversation> {
  const body: Record<string, any> = {
    persona_id: personaId,
    user_persona_id: options.userPersonaId || null,
    preset_id: options.presetId || null,
    template_id: options.templateId || null,
  }
  if (options.regexPresetId) body.regex_preset_id = options.regexPresetId
  if (options.worldbookIds !== undefined) body.worldbook_ids = options.worldbookIds
  if (options.title) body.title = options.title
  if (typeof options.greetingIndex === 'number') body.greeting_index = options.greetingIndex
  const res = await api.post('/v1/conversations', body)
  return res.data
}

export async function deleteConversation(id: string): Promise<void> {
  await api.delete(`/v1/conversations/${id}`)
}

export async function applyPreset(convId: string, presetId: string | null): Promise<Conversation> {
  const res = await api.put(`/v1/conversations/${convId}/apply-preset`, { preset_id: presetId })
  return res.data
}

export async function updateConversationConfig(convId: string, chatConfig: ChatConfig): Promise<Conversation> {
  const res = await api.put(`/v1/conversations/${convId}/config`, { chat_config: chatConfig })
  return res.data
}

export async function switchRegexPreset(convId: string, regexPresetId: string | null): Promise<Conversation> {
  const res = await api.put(`/v1/conversations/${convId}/regex-preset`, { regex_preset_id: regexPresetId })
  return res.data
}

export async function fetchRegexScripts(convId: string): Promise<RegexScript[]> {
  const res = await api.get(`/v1/conversations/${convId}/regex-scripts`)
  return res.data.scripts || []
}

/**
 * 切换开场白。仅在对话尚未开始（用户未回复过）时可用。
 * greeting_index: 0 = first_message，>=1 = alternate_greetings[idx-1]。
 * 详见 ADR-0017。
 */
export async function switchGreeting(
  convId: string,
  greetingIndex: number,
): Promise<{ message_id: string; content: string; display_content?: string | null }> {
  const res = await api.put(`/v1/conversations/${convId}/greeting`, {
    greeting_index: greetingIndex,
  })
  return res.data
}


export async function switchTemplate(convId: string, templateId: string | null): Promise<Conversation> {
  const res = await api.put(`/v1/conversations/${convId}/template`, { template_id: templateId })
  return res.data
}

export async function updateConversationToggles(
  convId: string, toggles: { analyze_emotion?: boolean },
): Promise<Conversation> {
  const res = await api.patch(`/v1/conversations/${convId}/toggles`, toggles)
  return res.data
}

// DELETE /v1/conversations/{id}/variables — 清空对话级 MVU 变量（ADR-0009）
export async function clearConversationVariables(convId: string): Promise<Conversation> {
  const res = await api.delete(`/v1/conversations/${convId}/variables`)
  return res.data
}

// POST /v1/conversations/{id}/variables/reload-mvu-initial-state — 缺失合并式重载 MVU 初始状态
export async function reloadMvuInitialState(convId: string): Promise<Conversation> {
  const res = await api.post(`/v1/conversations/${convId}/variables/reload-mvu-initial-state`)
  return res.data
}

// PUT /v1/conversations/{id}/mvu-state — ADR-0008c UP 通道：浏览器 MVU Host 结算的 stat_data 回传持久化
export async function updateMvuState(convId: string, statData: Record<string, any>): Promise<Conversation> {
  const res = await api.put(`/v1/conversations/${convId}/mvu-state`, { stat_data: statData })
  return res.data
}

// ── ADR-0008d：MVU 卡 UI 危险能力 per-conversation 开关 + 卡能力后端端点（provider）──

// PATCH /v1/conversations/{id}/mvu-capabilities — 开/关某会话的危险能力（卡调 LLM / 改会话）
export async function setMvuCapabilities(convId: string, dangerous: boolean): Promise<Conversation> {
  const res = await api.patch(`/v1/conversations/${convId}/mvu-capabilities`, { dangerous })
  return res.data
}

// read：getWorldbook —— 会话绑定世界书条目（只读）
export async function mvuGetWorldbook(convId: string, name?: string): Promise<any[]> {
  const res = await api.get(`/v1/conversations/${convId}/mvu/worldbook`, { params: name ? { name } : {} })
  return res.data
}

// read：getChatMessages —— 按 TavernHelper id/range 读会话楼层
export async function mvuGetChatMessages(convId: string, range: string): Promise<any[]> {
  const res = await api.get(`/v1/conversations/${convId}/mvu/chat-messages`, { params: { range } })
  return res.data
}

// dangerous：generateRaw —— 卡触发 LLM 生成（后端忽略卡自带 custom_api，用 EMIYA LLM + 封顶 token）
export async function mvuGenerateRaw(convId: string, config: Record<string, any>): Promise<{ text: string }> {
  const res = await api.post(`/v1/conversations/${convId}/mvu/generate`, config)
  return res.data
}

// dangerous：createChatMessages —— 卡往会话追加楼层（带 per-message data）
export async function mvuCreateChatMessages(convId: string, messages: any[], insertBefore?: number | null): Promise<any[]> {
  const res = await api.post(`/v1/conversations/${convId}/mvu/chat-messages`, { messages, insert_before: insertBefore ?? null })
  return res.data
}

// dangerous：setChatMessages —— 按 message_id 改楼层文本/data
export async function mvuSetChatMessages(convId: string, messages: any[]): Promise<any[]> {
  const res = await api.patch(`/v1/conversations/${convId}/mvu/chat-messages`, { messages })
  return res.data
}

// dangerous：deleteChatMessages —— 按 message_id 删楼层
export async function mvuDeleteChatMessages(convId: string, messageIds: number[]): Promise<{ deleted: number }> {
  const res = await api.delete(`/v1/conversations/${convId}/mvu/chat-messages`, { data: { message_ids: messageIds } })
  return res.data
}
