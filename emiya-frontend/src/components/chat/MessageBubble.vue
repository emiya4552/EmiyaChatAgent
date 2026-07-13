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
        <div
          v-if="contractBadge"
          class="oc-badge"
          :class="contractBadge.cls"
          :title="contractBadge.tip"
        >
          {{ contractBadge.label }}
        </div>
      </div>
      <img
        v-if="message.role === 'user' && authStore.user?.avatar_url"
        class="avatar user-avatar"
        :src="authStore.user.avatar_url"
        :alt="authStore.user.nickname || '用户'"
      />
      <div v-else-if="message.role === 'user'" class="avatar user-avatar" :style="{ background: userAvatarColor(authStore.user?.nickname || '我') }">
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

// ADR-0003 双管线：优先渲染后端派生的 display_content（markdownOnly 美化后，含
// 状态栏 HTML / UpdateVariable 折叠等）；流式期间和老消息 display_content 为空时
// 回退 content。前端仍不做"渲染时正则替换"，正则由后端分 prompt/显示两批跑。
const displayContent = computed(() =>
  props.message.display_content != null
    ? props.message.display_content
    : props.message.content,
)

const avatarBg = computed(() => avatarColor(props.personaName || 'AI'))
const avatarInitial = computed(() => (props.personaName || 'AI')[0])

function userAvatarColor(name: string): string {
  return avatarColor(name)
}

const formattedTime = computed(() => {
  const d = new Date(props.message.created_at)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
})

// 可见输出契约徽章（ADR-1f 稳定诊断结构）：仅 assistant 消息、本轮有激活契约时显示。
const contractBadge = computed(() => {
  const oc = props.message.output_contract
  if (!oc || !oc.contract_mode || oc.contract_mode === 'none') return null
  if (oc.outcome === 'disabled') return null // off / 无契约不打扰
  const outcome = oc.outcome
  const method = oc.method ?? 'initial'
  const repaired = method !== 'initial'
  let label = '格式契约'
  let cls = 'ok'
  if (outcome === 'conflict') {
    label = '格式契约冲突'
    cls = 'fail'
  } else if (outcome === 'passed' && oc.coverage === 'partial') {
    label = repaired ? '格式已修复（部分保证）' : '格式 ✓（部分保证）'
    cls = repaired ? 'fixed' : 'ok'
  } else if (outcome === 'passed' && repaired) {
    label = '格式已修复'
    cls = 'fixed'
  } else if (outcome === 'passed') {
    label = '格式 ✓'
    cls = 'ok'
  } else if (outcome === 'failed') {
    label = '格式未满足'
    cls = 'fail'
  }
  const bits: string[] = []
  if (oc.coverage) bits.push(`覆盖:${oc.coverage}`)
  if (method) bits.push(`方式:${method}`)
  // strict 降级等：请求模式与实际生效模式不一致时提示（ADR-1f）。
  if (oc.requested_mode && oc.effective_mode && oc.requested_mode !== oc.effective_mode) {
    bits.push(`模式:${oc.requested_mode}→${oc.effective_mode}`)
  }
  const conflicts = Array.isArray(oc.conflicts) ? oc.conflicts.length : 0
  if (conflicts) bits.push(`冲突:${conflicts}`)
  if (oc.extra_calls) bits.push(`额外调用:${oc.extra_calls}`)
  const guaranteed = Array.isArray(oc.guaranteed_rules) ? oc.guaranteed_rules.length : 0
  const soft = Array.isArray(oc.soft_rules) ? oc.soft_rules.length : 0
  if (guaranteed || soft) bits.push(`程序保证:${guaranteed} 软:${soft}`)
  return { label, cls, tip: bits.join(' · ') || '本轮可见输出契约' }
})
</script>

<style scoped>
.oc-badge {
  display: inline-block;
  margin-top: 6px;
  padding: 1px 8px;
  font-size: 11px;
  line-height: 1.6;
  border-radius: 10px;
  cursor: default;
  user-select: none;
}
.oc-badge.ok {
  color: #16a34a;
  background: rgba(22, 163, 74, 0.12);
}
.oc-badge.fixed {
  color: #2563eb;
  background: rgba(37, 99, 235, 0.12);
}
.oc-badge.fail {
  color: #d97706;
  background: rgba(217, 119, 6, 0.14);
}
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
  object-fit: cover;
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
