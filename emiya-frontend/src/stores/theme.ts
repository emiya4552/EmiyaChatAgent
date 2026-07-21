import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ThemeMode = 'day' | 'night'

const STORAGE_KEY = 'emiya-theme'

function readStored(): ThemeMode {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'day' || saved === 'night') return saved
  // 首次访问跟随系统偏好,默认日间(暖色米纸)
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'night'
  return 'day'
}

/**
 * 日/夜主题:把 data-theme 写到 <html>,令 variables.css 的
 * :root[data-theme="night"] 覆盖生效(含 naive-ui 挂在 body 的浮层)。
 * 与 useCssThemeInjection(用户级 / 角色卡级自定义 CSS,ADR-0008)正交。
 */
export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(readStored())

  function apply() {
    document.documentElement.setAttribute('data-theme', mode.value)
  }

  function set(next: ThemeMode) {
    mode.value = next
    localStorage.setItem(STORAGE_KEY, next)
    apply()
  }

  function toggle() {
    set(mode.value === 'night' ? 'day' : 'night')
  }

  // 立即应用一次(store 创建即在 <html> 上落地当前主题)
  apply()

  return { mode, set, toggle, apply }
})
