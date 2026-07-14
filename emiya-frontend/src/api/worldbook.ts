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

export async function detectWorldbookEntryOutputContract(
  id: string,
  entryUid: number,
): Promise<Worldbook> {
  const res = await api.post(`/v1/worldbooks/${id}/entries/${entryUid}/detect-output-contract`)
  return res.data
}

// ─── 输出契约声明 / canonical section（ADR-2b）───

export interface CanonicalSection {
  name: string
  label: string
  kind: string
  marker: string
  order: number
}

export async function fetchCanonicalSections(): Promise<CanonicalSection[]> {
  const res = await api.get('/v1/worldbooks/output-contract/canonical-sections')
  return res.data
}

/** 用户显式声明输出模板（source=manual, reviewed=true，最高权威）。 */
export async function declareWorldbookEntryOutputContract(
  id: string,
  entryUid: number,
  body: { mode: string; section_names: string[] },
): Promise<Worldbook> {
  const res = await api.put(`/v1/worldbooks/${id}/entries/${entryUid}/output-contract`, body)
  return res.data
}

/** 把现有识别结果确认为 reviewed=true（只提权威性，不改内容）。 */
export async function confirmWorldbookEntryOutputContract(
  id: string,
  entryUid: number,
): Promise<Worldbook> {
  const res = await api.post(`/v1/worldbooks/${id}/entries/${entryUid}/confirm-output-contract`)
  return res.data
}

export async function updateWorldbookEntryOutputContract(
  id: string,
  entryUid: number,
  body: { definition?: Record<string, unknown>; enabled?: boolean },
): Promise<Worldbook> {
  const res = await api.patch(`/v1/worldbooks/${id}/entries/${entryUid}/output-contract`, body)
  return res.data
}

export async function restoreWorldbookEntryOutputContractAuto(
  id: string,
  entryUid: number,
): Promise<Worldbook> {
  const res = await api.post(`/v1/worldbooks/${id}/entries/${entryUid}/restore-auto-output-contract`)
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
