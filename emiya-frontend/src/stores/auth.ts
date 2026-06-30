import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, UserUpdateRequest } from '../types'
import * as authApi from '../api/auth'
import { updateMe } from '../api/user'
import type { LoginRequest, RegisterRequest } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<User | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  // 从 localStorage 恢复登录状态（store 创建时自动调用）
  function initFromStorage() {
    const stored = localStorage.getItem('user')
    if (stored) {
      try {
        user.value = JSON.parse(stored)
      } catch {
        localStorage.removeItem('user')
      }
    }
  }
  initFromStorage()

  // 登录
  async function loginAction(data: LoginRequest) {
    const res = await authApi.login(data)
    token.value = res.access_token
    user.value = res.user
    localStorage.setItem('token', res.access_token)
    localStorage.setItem('user', JSON.stringify(res.user))
  }

  // 注册
  async function registerAction(data: RegisterRequest) {
    const res = await authApi.register(data)
    token.value = res.access_token
    user.value = res.user
    localStorage.setItem('token', res.access_token)
    localStorage.setItem('user', JSON.stringify(res.user))
  }

  // 退出登录
  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  // 刷新用户信息
  async function fetchMeAction() {
    try {
      const u = await authApi.fetchMe()
      user.value = u
      localStorage.setItem('user', JSON.stringify(u))
    } catch {
      logout()
    }
  }

  // PATCH /users/me — 用于编辑昵称/头像/CSS 主题（详见 ADR-0008）
  async function updateMeAction(data: UserUpdateRequest) {
    const u = await updateMe(data)
    user.value = u
    localStorage.setItem('user', JSON.stringify(u))
  }

  return {
    token,
    user,
    isAuthenticated,
    initFromStorage,
    login: loginAction,
    register: registerAction,
    logout,
    fetchMe: fetchMeAction,
    updateMe: updateMeAction,
  }
})
