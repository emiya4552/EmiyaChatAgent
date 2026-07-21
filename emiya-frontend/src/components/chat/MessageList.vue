<template>
  <div class="message-list-wrap">
    <div class="message-list" ref="listRef">
      <!-- 内容包裹层：ResizeObserver 观察它的高度变化（滚动容器本身高度固定，测不到内容撑高） -->
      <div class="message-list-content" ref="contentRef">
        <div v-if="chatStore.hasMoreMessages" class="load-earlier">
          <n-button text type="primary" @click="handleLoadEarlier">
            加载更早的消息
          </n-button>
        </div>
        <MessageBubble
          v-for="(msg, idx) in messages"
          :key="msg.id"
          :data-msg-id="msg.id"
          :message="msg"
          :is-last="idx === messages.length - 1"
          :show-timestamp="shouldShowTimestamp(idx)"
          :persona-name="personaName"
          :persona-avatar-url="personaAvatarUrl"
          :greeting-nav="idx === 0 ? greetingNav : undefined"
        />
      </div>
    </div>

    <div v-if="messages.length === 0" class="empty-hint">
      <p>开始新对话吧~</p>
    </div>

    <!-- 不在底部时出现「回到底部」悬浮按钮；流式生成中额外提示有新内容 -->
    <transition name="scroll-btn-fade">
      <button
        v-if="!isAtBottom && messages.length > 0"
        type="button"
        class="scroll-bottom-btn"
        :class="{ pulsing: chatStore.isStreaming }"
        aria-label="回到最新消息"
        title="回到最新消息"
        @click="scrollToBottom(true)"
      >
        <span aria-hidden="true">↓</span>
      </button>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { watch, ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import type { Message } from '../../types'
import MessageBubble from './MessageBubble.vue'
import { NButton } from 'naive-ui'
import { useChatStore } from '../../stores/chat'
import { useConversationStore } from '../../stores/conversation'
import { useChatUiStore } from '../../stores/chatUi'

const props = defineProps<{
  messages: Message[]
  personaName: string
  personaAvatarUrl: string | null
  /** 开场白切换 navigator（ADR-0017）；仅当 ChatMain 判定可切时传入，
   * MessageList 透传给 idx=0 的 MessageBubble。 */
  greetingNav?: {
    idx: number
    total: number
    busy: boolean
    onChange: (newIdx: number) => void
  }
}>()

const chatStore = useChatStore()
const convStore = useConversationStore()
const chatUi = useChatUiStore()
const listRef = ref<HTMLElement>()
const contentRef = ref<HTMLElement>()

// 距底 ≤ 该阈值即视为"在底部"：容忍行高/图片加载带来的零点几像素误差，也让
// 用户轻微上滑时不至于马上判定为"离开底部"。
const BOTTOM_THRESHOLD = 80
const isAtBottom = ref(true)

// 本实例绑定的对话 id：MessageList 以 :key=currentId 挂载，故实例与对话一一对应。
// 存/取滚动位置一律用它，而非实时 convStore.currentId——切对话时旧实例 onBeforeUnmount
// 触发的那一刻 currentId 已指向新对话，用实时值会把位置存错对话。
const myConvId = convStore.currentId
let didInitialPosition = false
let saveTimer: ReturnType<typeof setTimeout> | null = null
let resizeObserver: ResizeObserver | null = null

function computeAtBottom(): boolean {
  const el = listRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_THRESHOLD
}

function scrollToBottom(smooth = false) {
  const el = listRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  isAtBottom.value = true
}

// 视口顶部那条消息作为锚点：记录它相对滚动容器顶的偏移。恢复时把同一条消息放回同一
// 偏移，即使其它消息异步撑高也不漂移。找不到（列表变了）时回退到裸 scrollTop。
function findTopAnchor(): { id: string; offset: number } | null {
  const el = listRef.value
  if (!el) return null
  const containerTop = el.getBoundingClientRect().top
  const rows = el.querySelectorAll<HTMLElement>('[data-msg-id]')
  for (const row of rows) {
    const rect = row.getBoundingClientRect()
    if (rect.bottom > containerTop + 1) {
      return { id: row.getAttribute('data-msg-id') || '', offset: rect.top - containerTop }
    }
  }
  return null
}

function applyAnchor(anchorId: string | null, anchorOffset: number, rawTop: number) {
  const el = listRef.value
  if (!el) return
  if (anchorId) {
    const row = el.querySelector<HTMLElement>(`[data-msg-id="${CSS.escape(anchorId)}"]`)
    if (row) {
      const containerTop = el.getBoundingClientRect().top
      el.scrollTop += row.getBoundingClientRect().top - containerTop - anchorOffset
      isAtBottom.value = computeAtBottom()
      return
    }
  }
  el.scrollTop = rawTop // 锚点消息不在了（如临时流式消息已被真 id 替换）→ 回退到裸 scrollTop
  isAtBottom.value = computeAtBottom()
}

function savePosition() {
  const el = listRef.value
  if (!el || !myConvId) return
  if (computeAtBottom()) {
    chatUi.saveScrollPosition(myConvId, { atBottom: true, anchorId: null, anchorOffset: 0, scrollTop: 0 })
    return
  }
  const anchor = findTopAnchor()
  chatUi.saveScrollPosition(myConvId, {
    atBottom: false,
    anchorId: anchor?.id || null,
    anchorOffset: anchor ? anchor.offset : 0,
    scrollTop: el.scrollTop,
  })
}

function onScroll() {
  isAtBottom.value = computeAtBottom()
  if (saveTimer) return
  saveTimer = setTimeout(() => {
    saveTimer = null
    savePosition()
  }, 150)
}

// 内容高度变化（图片/代码块 iframe 异步撑高、流式增量、新消息）：只要"意图贴底"就持续
// 钉住底部——这是切对话/返回后能真正停在最新消息、以及流式跟随的关键。首次定位前不干预。
function onContentResize() {
  if (!didInitialPosition) return
  if (isAtBottom.value) scrollToBottom()
}

// 首次定位（消息就绪后）：有"离开时非贴底"的记忆则按锚点恢复，否则滚到最新消息。
async function positionInitial() {
  if (didInitialPosition) return
  didInitialPosition = true
  const saved = myConvId ? chatUi.getScrollPosition(myConvId) : undefined
  // 预置意图：非贴底恢复时先关掉 isAtBottom，避免 ResizeObserver 初次回调把视图钉到底部再跳回锚点
  if (saved && !saved.atBottom) isAtBottom.value = false
  await nextTick()
  const el = listRef.value
  if (!el) return
  if (saved && !saved.atBottom) {
    // 异步内容撑高会漂移锚点，短时间内多帧校正（用户此刻极少滚动，窗口很短）。
    applyAnchor(saved.anchorId, saved.anchorOffset, saved.scrollTop)
    let frames = 0
    const reapply = () => {
      if (frames++ > 18) return
      applyAnchor(saved.anchorId, saved.anchorOffset, saved.scrollTop)
      requestAnimationFrame(reapply)
    }
    requestAnimationFrame(reapply)
  } else {
    scrollToBottom()
  }
}

function shouldShowTimestamp(idx: number): boolean {
  if (idx === 0) return false
  const prev = props.messages[idx - 1]
  const curr = props.messages[idx]
  return new Date(curr.created_at).toDateString() !== new Date(prev.created_at).toDateString()
}

// 上滑加载更早消息：往列表顶部插入内容会改变 scrollHeight，补偿 scrollTop 保持视觉锚点，
// 避免"加载后阅读位置突然下跳"。
async function handleLoadEarlier() {
  const el = listRef.value
  if (!convStore.currentId || !el) return
  const prevHeight = el.scrollHeight
  const prevTop = el.scrollTop
  await chatStore.loadEarlierMessages(convStore.currentId)
  await nextTick()
  if (listRef.value) listRef.value.scrollTop = prevTop + (listRef.value.scrollHeight - prevHeight)
}

// 新消息到达：首次填充触发定位；用户本人发送（sendMessage 会同步追加一条 user 消息）时
// 无条件滚到底部——发消息即想看到回复。其余"贴底跟随"由 ResizeObserver 统一处理。
watch(
  () => props.messages.length,
  (len, oldLen) => {
    if (!didInitialPosition) {
      if (len > 0) positionInitial()
      return
    }
    if (len <= oldLen) return
    if (props.messages.slice(oldLen).some((m) => m.role === 'user')) {
      nextTick(() => scrollToBottom())
    }
  },
)

onMounted(() => {
  listRef.value?.addEventListener('scroll', onScroll, { passive: true })
  if (contentRef.value) {
    resizeObserver = new ResizeObserver(onContentResize)
    resizeObserver.observe(contentRef.value)
  }
  if (props.messages.length > 0) positionInitial()
})

onBeforeUnmount(() => {
  savePosition()
  listRef.value?.removeEventListener('scroll', onScroll)
  resizeObserver?.disconnect()
  resizeObserver = null
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
})
</script>

<style scoped>
.message-list-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 24px clamp(24px, 8vw, 160px);
  box-sizing: border-box;
  background: var(--color-bg-page);
  animation: fade-in 0.15s ease;
}
/* 内容包裹层：建立 BFC 防止子项外边距塌陷穿透，撑满高度以让空状态仍能居中 */
.message-list-content {
  display: flow-root;
  min-height: 100%;
}

@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
.load-earlier {
  text-align: center;
  padding: 8px 0;
}
.empty-hint {
  position: absolute;
  inset: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  color: var(--color-text-placeholder);
  font-size: 16px;
  pointer-events: none;
}

/* 回到底部悬浮按钮：贴在滚动区右下角（输入框上方），仅在未贴底时出现 */
.scroll-bottom-btn {
  position: absolute;
  right: clamp(16px, 4vw, 40px);
  bottom: 20px;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  color: var(--color-primary);
  border: 1px solid var(--color-border);
  border-radius: 50%;
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-md);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  transition: transform var(--transition-fast), background var(--transition-fast), color var(--transition-fast);
}
.scroll-bottom-btn:hover {
  color: #fffaf4;
  background: var(--color-primary);
  border-color: var(--color-primary);
  transform: translateY(-1px);
}
.scroll-bottom-btn:active { transform: translateY(1px); }
/* 流式生成中且用户离开底部：轻微脉冲提示"下方有新内容正在生成" */
.scroll-bottom-btn.pulsing { animation: scroll-btn-pulse 1.4s ease-in-out infinite; }
@keyframes scroll-btn-pulse {
  0%, 100% { box-shadow: var(--shadow-md); }
  50% { box-shadow: 0 5px 14px rgba(74, 54, 32, 0.09), 0 0 0 5px var(--color-primary-light); }
}
.scroll-btn-fade-enter-active,
.scroll-btn-fade-leave-active { transition: opacity var(--transition-fast), transform var(--transition-fast); }
.scroll-btn-fade-enter-from,
.scroll-btn-fade-leave-to { opacity: 0; transform: translateY(6px); }

@media (max-width: 720px) {
  .message-list { padding: 18px 12px; }
}
</style>
