import api from './index'
import type { PresetInfo, PresetDetail } from '../types'

export async function fetchPresets(): Promise<PresetInfo[]> {
  const res = await api.get('/v1/presets')
  return res.data
}

export async function fetchPresetDetail(id: string): Promise<PresetDetail> {
  const res = await api.get(`/v1/presets/${encodeURIComponent(id)}`)
  return res.data
}

export async function createPreset(data: Partial<PresetDetail>): Promise<PresetDetail> {
  const res = await api.post('/v1/presets', data)
  return res.data
}

export async function updatePreset(id: string, data: Partial<PresetDetail>): Promise<PresetDetail> {
  const res = await api.put(`/v1/presets/${encodeURIComponent(id)}`, data)
  return res.data
}

export async function deletePreset(id: string): Promise<void> {
  await api.delete(`/v1/presets/${encodeURIComponent(id)}`)
}

export async function importPreset(file: File): Promise<PresetDetail> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await api.post('/v1/presets/import', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}
