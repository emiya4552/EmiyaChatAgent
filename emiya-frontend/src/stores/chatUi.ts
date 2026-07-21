import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 聊天顶部工具栏与工作区之间的轻量 UI 状态。
 * 弹窗动作使用自增信号，保证连续点击同一入口也能被 watch 捕获；回复长度与
 * 卡 UI 显隐则是两边共同消费的持久状态，避免 AppNav / ChatMain 各存一份。
 */
export const useChatUiStore = defineStore('chatUi', () => {
  const newConvSignal = ref(0)
  const openConfigSignal = ref(0)
  const replyLength = ref<'short' | 'medium' | 'long'>(
    (localStorage.getItem('emiya_reply_length') as 'short' | 'medium' | 'long' | null) || 'medium',
  )
  const cardUiVisible = ref(true)

  // 按对话记忆消息列表的滚动位置：仅存活于本次 SPA 会话（内存态，刷新即弃）。
  // 用途：离开 /chat 去别的页面（如账户设置）再返回时，恢复离开时的阅读位置。
  // atBottom=true 表示离开时停在最新消息处——返回继续贴底（含期间到达的新消息）；否则
  // 以"视口顶部那条消息的 id + 其相对偏移"为锚点恢复，能抵抗图片/代码块 iframe 异步撑高
  // 造成的位置漂移（anchorId 为空时回退到原始 anchorOffset=scrollTop）。
  type ScrollPos = { atBottom: boolean; anchorId: string | null; anchorOffset: number; scrollTop: number }
  const scrollPositions = ref<Record<string, ScrollPos>>({})

  function setReplyLength(value: 'short' | 'medium' | 'long') {
    replyLength.value = value
    localStorage.setItem('emiya_reply_length', value)
  }

  return {
    newConvSignal,
    openConfigSignal,
    replyLength,
    cardUiVisible,
    scrollPositions,
    requestNewConv: () => { newConvSignal.value++ },
    requestOpenConfig: () => { openConfigSignal.value++ },
    setReplyLength,
    toggleCardUi: () => { cardUiVisible.value = !cardUiVisible.value },
    saveScrollPosition: (convId: string, pos: ScrollPos) => { scrollPositions.value[convId] = pos },
    getScrollPosition: (convId: string): ScrollPos | undefined => scrollPositions.value[convId],
    // 切换到某对话时清掉它的记忆位置，强制该对话下次挂载滚到最新消息（切对话 ≠ 路由往返）
    forgetScrollPosition: (convId: string) => { delete scrollPositions.value[convId] },
  }
})
