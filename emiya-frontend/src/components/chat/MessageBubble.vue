<template>
  <div>
    <div v-if="showTimestamp" class="timestamp-divider">
      <span>{{ formattedTime }}</span>
    </div>
    <div :class="['message-bubble', message.role, { 'message-enter': isLast }]">
      <img v-if="message.role === 'assistant' && personaAvatarUrl" class="avatar" :src="personaAvatarUrl" :alt="personaName" />
      <div v-else-if="message.role === 'assistant'" class="avatar" :style="{ background: avatarBg }">
        {{ avatarInitial }}
      </div>
      <div class="bubble-content">
        <template v-if="message.role === 'assistant' && isStreamingMsg">
          <StreamingText :text="displayContent" :is-streaming="true" />
        </template>
        <template v-else>
          <StreamingText :text="displayContent" :is-streaming="false" />
        </template>
        <!-- 开场白左右切换器（ADR-0017）：仅在 ChatMain 判定可切时传 prop，
             否则整块不渲染。点击 < / > 调后端 switchGreeting 替换本条 content -->
        <div v-if="greetingNav && greetingNav.total > 1" class="greeting-nav">
          <button
            class="greeting-nav-btn"
            :disabled="greetingNav.busy || greetingNav.idx <= 0"
            :title="'上一个开场白'"
            @click="onGreetingPrev"
          >‹</button>
          <span class="greeting-nav-count">
            {{ greetingNav.idx + 1 }} / {{ greetingNav.total }}
          </span>
          <button
            class="greeting-nav-btn"
            :disabled="greetingNav.busy || greetingNav.idx >= greetingNav.total - 1"
            :title="'下一个开场白'"
            @click="onGreetingNext"
          >›</button>
        </div>
      </div>
      <div v-if="message.role === 'user'" class="avatar user-avatar" :style="{ background: userAvatarColor(authStore.user?.nickname || '我') }">
        {{ authStore.user?.nickname?.charAt(0) || '我' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '../../types'
import StreamingText from './StreamingText.vue'
import { useChatStore } from '../../stores/chat'
import { useAuthStore } from '../../stores/auth'
import { avatarColor } from '../../utils/avatar'

interface GreetingNav {
  idx: number          // 当前激活的开场白索引 (0 = first_message, >=1 = alt[idx-1])
  total: number        // 1 + alternate_greetings.length
  busy: boolean        // 切换 API 正在请求中（防双击）
  onChange: (newIdx: number) => void  // 父组件传入；MessageBubble 不直接调 API
}

const props = defineProps<{
  message: Message
  isLast: boolean
  showTimestamp: boolean
  personaName: string
  personaAvatarUrl: string | null
  /** 开场白切换器配置；ADR-0017：仅在"首条 assistant + 该 persona 有 alt
   * + 用户还没回复"时由父组件传入，否则不渲染按钮组 */
  greetingNav?: GreetingNav
}>()

function onGreetingPrev() {
  if (!props.greetingNav || props.greetingNav.busy) return
  if (props.greetingNav.idx <= 0) return
  props.greetingNav.onChange(props.greetingNav.idx - 1)
}

function onGreetingNext() {
  if (!props.greetingNav || props.greetingNav.busy) return
  if (props.greetingNav.idx >= props.greetingNav.total - 1) return
  props.greetingNav.onChange(props.greetingNav.idx + 1)
}

const chatStore = useChatStore()
const authStore = useAuthStore()

const isStreamingMsg = computed(
  () => chatStore.isStreaming && props.isLast && props.message.role === 'assistant'
)

// ADR-0015：reply 正则已上移到后端 message_pipeline，DB 里的 content 即最终展示版本。
// 前端不再做"渲染时正则替换"——简化为直接显示 message.content。
const displayContent = computed(() => props.message.content)

const avatarBg = computed(() => avatarColor(props.personaName || 'AI'))
const avatarInitial = computed(() => (props.personaName || 'AI')[0])

function userAvatarColor(name: string): string {
  return avatarColor(name)
}

const formattedTime = computed(() => {
  const d = new Date(props.message.created_at)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
})
</script>

<style scoped>
.timestamp-divider {
  display: flex;
  justify-content: center;
  padding: 12px 0;
}
.timestamp-divider span {
  font-size: 12px;
  color: var(--color-text-tertiary);
  background: var(--color-bg-page);
  padding: 2px 12px;
  border-radius: 10px;
}
.message-bubble {
  display: flex;
  gap: 10px;
  padding: 6px 16px;
  max-width: 65%;
}
.message-bubble.user {
  margin-left: auto;
  flex-direction: row-reverse;
}
.message-bubble.assistant {
  margin-right: auto;
  /* AI 输出常含状态栏 / 角色卡这类长文本，65% 太挤 */
  max-width: 80%;
}
/* 注：含 iframe HTML 渲染时进一步拓宽的规则在文件底部的非-scoped 块里，
   因为 .th-html-render 是 markdown → v-html 注入的节点，没有 data-v 属性，
   scoped 选择器匹配不到。 */
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
}
.user-avatar {
  font-size: 14px;
}
.bubble-content {
  padding: 10px 14px;
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-sm);
  line-height: 1.6;
}
.assistant .bubble-content {
  border-left: 2px solid var(--color-primary);
}
.user .bubble-content {
  background: var(--color-primary-bg);
  color: var(--color-text);
}

.greeting-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--color-border-light, rgba(0, 0, 0, 0.08));
}
.greeting-nav-btn {
  width: 30px;
  height: 30px;
  border: 1px solid var(--color-border, #d9d9d9);
  background: var(--color-bg-surface, #fff);
  border-radius: 50%;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  color: var(--color-text-secondary, #555);
  transition: all var(--transition-fast, 0.15s);
}
.greeting-nav-btn:not(:disabled):hover {
  background: var(--color-primary-bg, #f0eaff);
  color: var(--color-primary, #7c5cfc);
  border-color: var(--color-primary, #7c5cfc);
}
.greeting-nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.greeting-nav-count {
  font-size: 12px;
  color: var(--color-text-tertiary, #888);
  min-width: 36px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.message-enter {
  animation: message-in 0.2s ease-out;
}

@keyframes message-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>

<!-- 非 scoped：用 :has 选择 v-html 注入的 .th-html-render 时，
     scoped 会给子选择器加 [data-v-xxx]，导致永远匹配不到。
     单独开一个全局块来绕过。.message-bubble.assistant 是本组件独有的复合
     class，不会污染其他组件。 -->
<style>
.message-bubble.assistant:has(.th-html-render) {
  max-width: 95%;
}
/* 同步让内部气泡填满，避免 bubble-content 自己 width:auto 时仍按内容收缩 */
.message-bubble.assistant:has(.th-html-render) .bubble-content {
  width: 100%;
}
</style>
