import api from './index'
import type {
  AuthorNoteUpdateRequest,
  Conversation,
  Worldbook,
  WorldbookCreateRequest,
  WorldbookListItem,
  WorldbookUpdateRequest,
} from '../types'

export async function fetchWorldbooks(): Promise<WorldbookListItem[]> {
  const res = await api.get('/v1/worldbooks')
  return res.data
}

export async function fetchWorldbook(id: string): Promise<Worldbook> {
  const res = await api.get(`/v1/worldbooks/${id}`)
  return res.data
}

export async function createWorldbook(body: WorldbookCreateRequest): Promise<Worldbook> {
  const res = await api.post('/v1/worldbooks', body)
  return res.data
}

export async function updateWorldbook(id: string, body: WorldbookUpdateRequest): Promise<Worldbook> {
  const res = await api.put(`/v1/worldbooks/${id}`, body)
  return res.data
}

export async function deleteWorldbook(id: string): Promise<void> {
  await api.delete(`/v1/worldbooks/${id}`)
}

export async function importWorldbook(file: File): Promise<Worldbook> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await api.post('/v1/worldbooks/import', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function exportWorldbook(id: string): Promise<{ filename: string; data: any }> {
  const res = await api.get(`/v1/worldbooks/${id}/export`)
  return res.data
}

// ─── 对话维度：绑定 / AN ───

export async function updateConversationWorldbooks(
  convId: string,
  worldbookIds: string[],
): Promise<Conversation> {
  const res = await api.put(`/v1/conversations/${convId}/worldbooks`, {
    worldbook_ids: worldbookIds,
  })
  return res.data
}

export async function updateConversationAuthorNote(
  convId: string,
  body: AuthorNoteUpdateRequest,
): Promise<Conversation> {
  const res = await api.put(`/v1/conversations/${convId}/author-note`, body)
  return res.data
}
