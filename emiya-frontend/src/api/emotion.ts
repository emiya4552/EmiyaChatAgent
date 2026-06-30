import api from './index'
import type {
  EmotionArcPoint,
  EmotionCalendarItem,
  EmotionDistributionItem,
  EmotionScopeConversation,
  EmotionScopePersona,
  EmotionTrendPoint,
} from '../types'

export interface EmotionFilters {
  persona_id?: string | null
  conversation_id?: string | null
}

// trend：当 conversation_id 给定时返回 EmotionArcPoint[]，否则 EmotionTrendPoint[]
export async function fetchEmotionTrend(
  days: number,
  filters: EmotionFilters = {},
): Promise<EmotionTrendPoint[] | EmotionArcPoint[]> {
  const params: Record<string, any> = { days }
  if (filters.persona_id) params.persona_id = filters.persona_id
  if (filters.conversation_id) params.conversation_id = filters.conversation_id
  const res = await api.get('/v1/emotions/trend', { params })
  return res.data
}

export async function fetchEmotionDistribution(
  days: number,
  filters: EmotionFilters = {},
): Promise<EmotionDistributionItem[]> {
  const params: Record<string, any> = { days }
  if (filters.persona_id) params.persona_id = filters.persona_id
  if (filters.conversation_id) params.conversation_id = filters.conversation_id
  const res = await api.get('/v1/emotions/distribution', { params })
  return res.data
}

export async function fetchEmotionCalendar(
  month: string,
  filters: EmotionFilters = {},
): Promise<EmotionCalendarItem[]> {
  const params: Record<string, any> = { month }
  if (filters.persona_id) params.persona_id = filters.persona_id
  if (filters.conversation_id) params.conversation_id = filters.conversation_id
  const res = await api.get('/v1/emotions/calendar', { params })
  return res.data
}

// Filter dropdown 数据源
export async function fetchScopePersonas(): Promise<EmotionScopePersona[]> {
  const res = await api.get('/v1/emotions/scope/personas')
  return res.data
}

export async function fetchScopeConversations(
  persona_id: string,
): Promise<EmotionScopeConversation[]> {
  const res = await api.get('/v1/emotions/scope/conversations', {
    params: { persona_id },
  })
  return res.data
}
