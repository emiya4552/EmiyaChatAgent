import api from './index'
import type { User, UserUpdateRequest } from '../types'

// PATCH /api/v1/users/me — 编辑当前用户资料（详见 docs/adr/0008）
export async function updateMe(data: UserUpdateRequest): Promise<User> {
  const res = await api.patch('/v1/users/me', data)
  return res.data
}

// POST /api/v1/users/me/avatar — 上传用户头像（multipart）
export async function uploadAvatar(file: File): Promise<User> {
  const form = new FormData()
  form.append('file', file)
  const res = await api.post('/v1/users/me/avatar', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

// POST /api/v1/users/me/change-password — 修改密码
export async function changePassword(
  old_password: string,
  new_password: string,
): Promise<void> {
  await api.post('/v1/users/me/change-password', { old_password, new_password })
}

// DELETE /api/v1/users/me — 注销账号（硬删全部数据，详见 ADR-0009）
export async function deleteMyAccount(password: string): Promise<void> {
  await api.delete('/v1/users/me', { data: { password } })
}
