<template>
  <div class="message-list" ref="listRef">
    <div v-if="chatStore.hasMoreMessages" class="load-earlier">
      <n-button text type="primary" @click="handleLoadEarlier">
        加载更早的消息
      </n-button>
    </div>
    <div v-if="messages.length === 0" class="empty-hint">
      <p>开始新对话吧~</p>
    </div>
    <MessageBubble
      v-for="(msg, idx) in messages"
      :key="msg.id"
      :message="msg"
      :is-last="idx === messages.length - 1"
      :show-timestamp="shouldShowTimestamp(idx)"
      :persona-name="personaName"
      :persona-avatar-url="personaAvatarUrl"
      :greeting-nav="idx === 0 ? greetingNav : undefined"
    />
  </div>
</template>

<script setup lang="ts">
import { watch, ref, nextTick } from 'vue'
import type { Message } from '../../types'
import MessageBubble from './MessageBubble.vue'
import { NButton } from 'naive-ui'
import { useChatStore } from '../../stores/chat'
import { useConversationStore } from '../../stores/conversation'

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
const listRef = ref<HTMLElement>()

function shouldShowTimestamp(idx: number): boolean {
  if (idx === 0) return true
  const prev = props.messages[idx - 1]
  const curr = props.messages[idx]
  const gap = new Date(curr.created_at).getTime() - new Date(prev.created_at).getTime()
  return gap > 5 * 60 * 1000
}

function handleLoadEarlier() {
  if (convStore.currentId) {
    chatStore.loadEarlierMessages(convStore.currentId)
  }
}

watch(
  () => [chatStore.messages.length, chatStore.streamingContent],
  async () => {
    await nextTick()
    if (listRef.value) {
      listRef.value.scrollTop = listRef.value.scrollHeight
    }
  },
  { deep: true }
)
</script>

<style scoped>
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  background: var(--color-bg-page);
  animation: fade-in 0.15s ease;
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
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  color: var(--color-text-placeholder);
  font-size: 16px;
}
</style>
