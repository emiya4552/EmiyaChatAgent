import api from './index'
import type { TemplateDetail, TemplateListItem, TemplateCreateRequest, TemplateUpdateRequest } from '../types'

export async function fetchTemplates(): Promise<TemplateListItem[]> {
  const { data } = await api.get('/v1/templates')
  return data
}

export async function fetchTemplate(id: string): Promise<TemplateDetail> {
  const { data } = await api.get(`/v1/templates/${id}`)
  return data
}

export async function createTemplate(req: TemplateCreateRequest): Promise<TemplateDetail> {
  const { data } = await api.post('/v1/templates', req)
  return data
}

export async function updateTemplate(id: string, req: TemplateUpdateRequest): Promise<TemplateDetail> {
  const { data } = await api.put(`/v1/templates/${id}`, req)
  return data
}

export async function deleteTemplate(id: string): Promise<void> {
  await api.delete(`/v1/templates/${id}`)
}

export async function duplicateTemplate(id: string): Promise<TemplateDetail> {
  const { data } = await api.post(`/v1/templates/${id}/duplicate`)
  return data
}

export async function exportTemplate(id: string): Promise<Record<string, any>> {
  const { data } = await api.get(`/v1/templates/${id}/export`)
  return data
}

// 拉内置默认模板的序列化（代码常量，非 DB 行）
export async function fetchDefaultPreview(): Promise<{
  name: string
  description: string
  is_builtin: boolean
  blocks: any[]
}> {
  const { data } = await api.get('/v1/templates/default-preview')
  return data
}
