import { watch, onUnmounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useConversationStore } from '../stores/conversation'
import { fetchPersonaDetail } from '../api/persona'

// CSS 主题注入：两层，各自包进具名 @layer（层顺序在 styles/variables.css 顶部声明：
// app-base < user-theme < card-theme）。优先级由 @layer 决定、无视特异性，所以卡样式
// 恒覆盖用户样式，且用户覆盖 :root 令牌在日/夜都生效。详见 docs/adr/0008。
//
//  - 用户级（user-theme）：全站生效，挂在 App 根、登录态常驻、跨路由不卸载。
//  - 角色卡级（card-theme）：聊天页作用域，随当前对话 persona 切换。

const USER_STYLE_ID = 'user-theme'
const PERSONA_STYLE_ID = 'persona-theme'

/**
 * 逃生舱：URL 带 ?safe 时跳过用户主题注入。
 * 用户把界面用自定义 CSS 搞坏后，访问任意页 + ?safe 即回到干净默认，必然能操作、能清空主题。
 */
export function isThemeSafeMode(): boolean {
  try {
    return new URLSearchParams(window.location.search).has('safe')
  } catch {
    return false
  }
}

function _setLayerStyle(
  id: string,
  layer: 'user-theme' | 'card-theme',
  css: string | null | undefined,
  insertAfterId?: string,
): void {
  let el = document.getElementById(id) as HTMLStyleElement | null
  if (!css || !css.trim()) {
    if (el) el.remove()
    return
  }
  if (!el) {
    el = document.createElement('style')
    el.id = id
    // 维持 DOM 顺序（persona 在 user 之后）——即便 @layer 已决定优先级也保持整洁。
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
  // 把用户/卡的裸 CSS 原样包进具名 layer；优先级交给 variables.css 的 @layer 顺序。
  // 注意：@layer 块内不允许 @import（须置于所有规则前）——v1 已知限制，见设置页提示。
  el.textContent = `@layer ${layer} {\n${css}\n}`
}

/**
 * 用户级全站主题注入。挂在 App 根：登录态存在即常驻，跨路由不卸载
 * （旧实现挂在 ChatView，导致离开聊天页主题被卸掉——已修正为全站）。
 */
export function useUserThemeInjection(): void {
  const authStore = useAuthStore()
  const safe = isThemeSafeMode()

  watch(
    () => authStore.user?.css_theme || null,
    (css) => _setLayerStyle(USER_STYLE_ID, 'user-theme', safe ? null : css),
    { immediate: true },
  )

  onUnmounted(() => {
    document.getElementById(USER_STYLE_ID)?.remove()
  })
}

/**
 * 角色卡级主题注入。挂在聊天页，随当前对话 persona 切换；对话切走即卸。
 * 当前 conversation list item 不带 css_theme，故 currentId 变化时按需 fetch persona detail。
 */
export function usePersonaThemeInjection(): void {
  const convStore = useConversationStore()

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
        _setLayerStyle(PERSONA_STYLE_ID, 'card-theme', null, USER_STYLE_ID)
        return
      }
      try {
        const detail = await fetchPersonaDetail(personaId)
        // 切换后又切回来的竞态：确认仍是最新选中
        if (lastPersonaId !== personaId) return
        _setLayerStyle(PERSONA_STYLE_ID, 'card-theme', detail.css_theme || null, USER_STYLE_ID)
      } catch {
        _setLayerStyle(PERSONA_STYLE_ID, 'card-theme', null, USER_STYLE_ID)
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    document.getElementById(PERSONA_STYLE_ID)?.remove()
  })
}
