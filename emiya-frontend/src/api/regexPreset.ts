import api from './index'
import type { RegexPresetInfo, RegexPresetDetail } from '../types'

export async function fetchRegexPresets(): Promise<RegexPresetInfo[]> {
  const res = await api.get('/v1/regex-presets')
  return res.data
}

export async function fetchRegexPresetDetail(id: string): Promise<RegexPresetDetail> {
  const res = await api.get(`/v1/regex-presets/${encodeURIComponent(id)}`)
  return res.data
}

export async function createRegexPreset(data: {
  name: string
  description?: string | null
  scripts?: Record<string, any>[]
}): Promise<RegexPresetDetail> {
  const res = await api.post('/v1/regex-presets', data)
  return res.data
}

export async function updateRegexPreset(
  id: string, data: { name?: string; description?: string | null; scripts?: Record<string, any>[] }
): Promise<RegexPresetDetail> {
  const res = await api.put(`/v1/regex-presets/${encodeURIComponent(id)}`, data)
  return res.data
}

export async function deleteRegexPreset(id: string): Promise<void> {
  await api.delete(`/v1/regex-presets/${encodeURIComponent(id)}`)
}

export async function importRegexPreset(file: File): Promise<RegexPresetDetail> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await api.post('/v1/regex-presets/import', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}
