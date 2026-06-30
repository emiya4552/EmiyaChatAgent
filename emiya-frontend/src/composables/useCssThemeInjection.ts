import { watch, onUnmounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useConversationStore } from '../stores/conversation'
import { fetchPersonaDetail } from '../api/persona'

// CSS 主题注入：把 User 级 + Persona 级 CSS 挂到 <head> 的两个 <style> 块
// 注入顺序保证：user 在前，persona 在后（CSS cascade → Persona 覆盖 User）
// 详见 docs/adr/0008

const USER_STYLE_ID = 'user-theme'
const PERSONA_STYLE_ID = 'persona-theme'

function _setStyle(id: string, css: string | null | undefined, insertAfterId?: string): void {
  let el = document.getElementById(id) as HTMLStyleElement | null
  if (!css || !css.trim()) {
    if (el) el.remove()
    return
  }
  if (!el) {
    el = document.createElement('style')
    el.id = id
    // 维持注入顺序：persona 在 user 之后挂；user 直接 append
    if (insertAfterId) {
      const after = document.getElementById(insertAfterId)
      if (after && after.parentNode) {
        after.parentNode.insertBefore(el, after.nextSibling)
      } else {
        document.head.appendChild(el)
      }
    } else {
      document.head.appendChild(el)
    }
  }
  el.textContent = css
}

export function useCssThemeInjection(): void {
  const authStore = useAuthStore()
  const convStore = useConversationStore()

  // User 级：跟随 authStore.user.css_theme
  watch(
    () => authStore.user?.css_theme || null,
    (css) => _setStyle(USER_STYLE_ID, css),
    { immediate: true },
  )

  // Persona 级：跟随当前对话的 ai_persona
  // 当前 conversation list item 没带 css_theme，所以在 currentId 变化时按需 fetch persona detail
  let lastPersonaId: string | null = null
  watch(
    () => {
      const id = convStore.currentId
      if (!id) return null
      const conv = convStore.list.find((c) => c.id === id)
      return conv?.persona_id || null
    },
    async (personaId) => {
      if (personaId === lastPersonaId) return
      lastPersonaId = personaId
      if (!personaId) {
        _setStyle(PERSONA_STYLE_ID, null, USER_STYLE_ID)
        return
      }
      try {
        const detail = await fetchPersonaDetail(personaId)
        // 切换发生后又切回来的情况：确认仍是最新选中
        if (lastPersonaId !== personaId) return
        _setStyle(PERSONA_STYLE_ID, detail.css_theme || null, USER_STYLE_ID)
      } catch {
        _setStyle(PERSONA_STYLE_ID, null, USER_STYLE_ID)
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    document.getElementById(USER_STYLE_ID)?.remove()
    document.getElementById(PERSONA_STYLE_ID)?.remove()
  })
}
