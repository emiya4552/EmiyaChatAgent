import api from './index'
import type { Relationship } from '../types'

/** 获取与某个人设的关系 */
export async function fetchRelationship(personaId: string): Promise<Relationship> {
  const res = await api.get(`/v1/relationships/${personaId}`)
  return res.data
}

/** 获取当前对话的关系 */
export async function fetchConversationRelationship(convId: string): Promise<Relationship> {
  const res = await api.get(`/v1/conversations/${convId}/relationship`)
  return res.data
}
