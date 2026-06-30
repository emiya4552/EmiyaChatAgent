import api from './index'
import type { Memory, MemoryListResponse, MemoryUpdateRequest } from '../types'

export async function fetchMemories(
  category?: string, scope?: string, memoryType?: string, limit = 20, offset = 0
): Promise<MemoryListResponse> {
  const params: Record<string, any> = { limit, offset }
  if (category) params.category = category
  if (scope) params.scope = scope
  if (memoryType) params.memory_type = memoryType
  const res = await api.get('/v1/memories', { params })
  return res.data
}

export async function fetchMemory(id: string): Promise<Memory> {
  const res = await api.get(`/v1/memories/${id}`)
  return res.data
}

export async function updateMemory(id: string, data: MemoryUpdateRequest): Promise<Memory> {
  const res = await api.put(`/v1/memories/${id}`, data)
  return res.data
}

export async function deleteMemory(id: string): Promise<void> {
  await api.delete(`/v1/memories/${id}`)
}

export async function clearAllMemories(): Promise<{ deleted: number }> {
  const res = await api.delete('/v1/memories')
  return res.data
}
