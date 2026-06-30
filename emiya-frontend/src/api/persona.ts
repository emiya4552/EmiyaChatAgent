import api from './index'
import type { PersonaListItem, PersonaDetail, PersonaCreateRequest, PersonaUpdateRequest, ImportParseResult } from '../types'

// 获取角色卡列表
export async function fetchPersonas(source?: 'template' | 'user' | 'all'): Promise<PersonaListItem[]> {
  const params: Record<string, string> = {}
  if (source) params.source = source
  const res = await api.get('/v1/personas', { params })
  return res.data
}

// 创建角色卡
export async function createPersona(data: PersonaCreateRequest): Promise<PersonaDetail> {
  const res = await api.post('/v1/personas', data)
  return res.data
}

// 更新角色卡
export async function updatePersona(id: string, data: PersonaUpdateRequest): Promise<PersonaDetail> {
  const res = await api.put(`/v1/personas/${id}`, data)
  return res.data
}

// 删除角色卡
export async function deletePersona(id: string): Promise<{
  deleted: boolean; affected_conversations: number; affected_memories: number;
}> {
  const res = await api.delete(`/v1/personas/${id}`)
  return res.data
}

// 获取角色卡详情
export async function fetchPersonaDetail(id: string): Promise<PersonaDetail> {
  const res = await api.get(`/v1/personas/${id}`)
  return res.data
}

// ─── 导入/导出 ───

// 解析角色卡（不入库）
export async function importParse(data: FormData): Promise<ImportParseResult> {
  const res = await api.post('/v1/personas/import/parse', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

// 确认导入
export async function importConfirm(data: FormData): Promise<{ persona: PersonaDetail; avatar_saved: boolean }> {
  const res = await api.post('/v1/personas/import/confirm', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

// 导出角色卡 PNG
export function exportPersonaUrl(id: string, format: string = 'png'): string {
  const base = api.defaults.baseURL || ''
  return `${base}/v1/personas/${id}/export?format=${format}`
}
