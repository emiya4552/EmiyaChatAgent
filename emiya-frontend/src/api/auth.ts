import api from './index'
import type { LoginRequest, MessageResponse, RegisterRequest, TokenResponse, User } from '../types'

// 用户登录
export async function login(data: LoginRequest): Promise<TokenResponse> {
  const res = await api.post('/v1/auth/login', data)
  return res.data
}

// 用户注册
export async function register(data: RegisterRequest): Promise<TokenResponse> {
  const res = await api.post('/v1/auth/register', data)
  return res.data
}

// 获取当前用户信息
export async function fetchMe(): Promise<User> {
  const res = await api.get('/v1/auth/me')
  return res.data
}

// 发送找回密码邮件
export async function forgotPassword(email: string): Promise<MessageResponse> {
  const res = await api.post('/v1/auth/forgot-password', { email })
  return res.data
}

// 使用邮件 token 重置密码
export async function resetPassword(token: string, newPassword: string): Promise<MessageResponse> {
  const res = await api.post('/v1/auth/reset-password', {
    token,
    new_password: newPassword,
  })
  return res.data
}
