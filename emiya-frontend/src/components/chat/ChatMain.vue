<template>
  <div class="chat-main">
    <!-- MVU 卡初始状态未成功播种时的非阻塞提示（不挡聊天，仅提示 + 一键重试）。
         判定：确为 MVU 卡（persona.uses_mvu）且对话级 mvu_state 未初始化。 -->
    <div v-if="mvuNeedsInit" class="mvu-init-banner">
      <span>⚠ 这张 MVU 卡的初始状态尚未成功播种，状态栏与变量可能缺失。</span>
      <button type="button" :disabled="reinitializing" @click="handleReinitMvu">
        {{ reinitializing ? '正在初始化…' : '重新初始化' }}
      </button>
    </div>

    <RelationshipBar
      v-if="currentConv && perceptionOn"
      ref="relationshipBarRef"
      :relationship="currentRelationship"
      :persona-name="currentConv.persona_name || ''"
      :mood="convStore.currentMood"
      :mood-intensity="convStore.moodIntensity"
    />

    <MilestoneMessage v-if="perceptionOn" :event="convStore.milestone" />

    <MessageList :key="convStore.currentId ?? undefined" :messages="chatStore.messages" :persona-name="currentConv?.persona_name || ''" :persona-avatar-url="personaAvatarUrl" :greeting-nav="greetingNav" />

    <!-- ADR-1g strict：草稿不流式，展示阶段状态直到最终文档一次性替换 -->
    <div v-if="chatStore.contractStage" class="contract-stage-bar">
      {{ contractStageLabel }}
    </div>

    <div v-if="chatStore.error" class="error-bar">
      {{ chatStore.error }}
    </div>

    <ChatInput
      :is-generating="chatStore.isStreaming"
      @send="handleSend"
      @stop="handleStop"
    />

    <n-modal :show="showConfigPanel" @update:show="showConfigPanel = $event">
      <div class="config-modal-card">
        <ConversationConfigPanel :visible="showConfigPanel" @close="showConfigPanel = false" />
      </div>
    </n-modal>

    <!-- ADR-0008d：卡 UI 右侧可折叠停靠栏（仅当卡有可渲染 UI 时显示） -->
    <MvuHostDock />

    <!-- ADR-0012 卡驱动"写入对话"：消息 HTML 在**同源**（无 sandbox）srcdoc iframe 里跑（见
         useHtmlIframeRender）。有些卡（角色创建自动开场、快速选项）靠 `window.parent.document` 找 ST 的
         `#send_textarea`/`#send_but` 自动发送。EMIYA 主 DOM 没这套 → 卡报 "SillyTavern UI not found" →
         退剪贴板。这里放一套**隐藏的等价发送 DOM**（卡设值+点 `#send_but` → 走 EMIYA 真实发送）。
         **仅当对话开启「卡界面危险能力」时挂载**：关闭时不放，保留卡自身"UI not found→剪贴板"降级（不回归）。 -->
    <form v-if="cardSendBridgeOn" id="send_form" class="card-send-bridge" aria-hidden="true" @submit.prevent="handleCardSend">
      <textarea id="send_textarea"></textarea>
      <div id="send_but" role="button" @click="handleCardSend"></div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useConversationStore } from '../../stores/conversation'
import { useChatStore } from '../../stores/chat'
import { useChatUiStore } from '../../stores/chatUi'
import { NModal, useMessage } from 'naive-ui'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'
import RelationshipBar from '../relationship/RelationshipBar.vue'
import MilestoneMessage from './MilestoneMessage.vue'
import ConversationConfigPanel from './ConversationConfigPanel.vue'
import MvuHostDock from './MvuHostDock.vue'
import { fetchConversationRelationship } from '../../api/relationship'
import { fetchPersonaDetail } from '../../api/persona'
import { switchGreeting, reloadMvuInitialState } from '../../api/conversation'
import type { Relationship, PersonaDetail } from '../../types'

const convStore = useConversationStore()
const chatStore = useChatStore()
const chatUi = useChatUiStore()

// ADR-1g strict 阶段状态文案。
const CONTRACT_STAGE_LABELS: Record<string, string> = {
  drafting: '正在创作草稿…',
  structuring: '正在结构化输出…',
  rendering: '正在渲染结构…',
  validating: '正在校验结构…',
  refilling: '正在补全缺失区块…',
}
const contractStageLabel = computed(
  () => CONTRACT_STAGE_LABELS[chatStore.contractStage] || '正在生成结构化回复…',
)
const msg = useMessage()

const showConfigPanel = ref(false)
const currentConv = computed(() =>
  convStore.list.find((c) => c.id === convStore.currentId) || null
)

watch(() => chatUi.openConfigSignal, () => {
  if (!currentConv.value) {
    msg.warning('请先选择或新建一个对话')
    return
  }
  showConfigPanel.value = true
})

// 感知系统开关（ADR-0020）：对话级 analyze_emotion 显式为 false 时，隐藏对话内的
// mood/关系条/里程碑指示器。必须显式判 !== false —— 历史开过感知的对话 DB 里已存
// current_mood/relationship 数据，只靠"有没有数据"判断会在关闭后仍露出指示器。
const perceptionOn = computed(() => currentConv.value?.analyze_emotion !== false)

// MVU 卡初始状态未播种的安全网：确为 MVU 卡（uses_mvu，来自已加载的 personaDetail）
// 且对话 mvu_state 未初始化时，给出非阻塞提示 + 一键重新播种。健康 MVU 卡 initialized
// 恒真 → 不显示；非 MVU 卡 uses_mvu=false → 不显示（不误报）。
const reinitializing = ref(false)
const mvuNeedsInit = computed(() =>
  currentPersonaDetail.value?.uses_mvu === true &&
  currentConv.value?.mvu_state?.initialized === false,
)

async function handleReinitMvu() {
  const id = convStore.currentId
  if (!id || reinitializing.value) return
  reinitializing.value = true
  try {
    const updated = await reloadMvuInitialState(id)
    const idx = convStore.list.findIndex((c) => c.id === id)
    if (idx !== -1) {
      convStore.list[idx] = {
        ...convStore.list[idx],
        mvu_state: updated.mvu_state,
        variables: updated.variables,
      }
    }
    msg.success('已重新初始化 MVU 状态')
  } catch {
    msg.error('重新初始化失败')
  } finally {
    reinitializing.value = false
  }
}

const personaAvatarUrl = computed(() => {
  return convStore.personaAvatarUrl(currentConv.value?.persona_id || null)
})

// ─── 开场白左右切换（ADR-0017）──────────────────────────────────
// 切对话时拉 personaDetail 拿 alternate_greetings；当 messages 里只有
// 一条且是 assistant（即用户还没回复过）时，给 MessageList 传 greetingNav。
const currentPersonaDetail = ref<PersonaDetail | null>(null)
const currentGreetingIdx = ref(0)
const greetingSwitching = ref(false)

async function loadPersonaDetail(conversationId: string) {
  const conversation = convStore.list.find((item) => item.id === conversationId)
  const personaId = conversation?.persona_id
  if (!personaId) {
    if (convStore.currentId === conversationId) currentPersonaDetail.value = null
    return
  }
  try {
    const detail = await fetchPersonaDetail(personaId)
    // 快速切换时旧请求可能后返回；只允许当前对话提交本地详情，避免开场白串台。
    if (convStore.currentId === conversationId) currentPersonaDetail.value = detail
  } catch {
    if (convStore.currentId === conversationId) currentPersonaDetail.value = null
  }
}

const greetingTotal = computed(() => {
  const d = currentPersonaDetail.value
  if (!d) return 0
  return 1 + (d.alternate_greetings?.length || 0)
})

const canSwitchGreeting = computed(() => {
  // 仅在"对话只有 1 条 assistant 消息"时允许切。
  // 一旦用户回复过，messages.length >= 2，按钮就自动消失。
  if (greetingTotal.value <= 1) return false
  const msgs = chatStore.messages
  if (msgs.length !== 1) return false
  if (msgs[0].role !== 'assistant') return false
  return true
})

const greetingNav = computed(() => {
  if (!canSwitchGreeting.value) return undefined
  return {
    idx: currentGreetingIdx.value,
    total: greetingTotal.value,
    busy: greetingSwitching.value,
    onChange: handleSwitchGreeting,
  }
})

async function handleSwitchGreeting(newIdx: number) {
  const convId = convStore.currentId
  if (!convId || greetingSwitching.value) return
  if (newIdx < 0 || newIdx >= greetingTotal.value) return
  greetingSwitching.value = true
  try {
    const res = await switchGreeting(convId, newIdx)
    // 用后端返回的清洗后文本替换本地 message[0]（content=prompt 版，
    // display_content=显示版，ADR-0003 双管线）
    const target = chatStore.messages.find(m => m.id === res.message_id)
    if (target) {
      target.content = res.content
      target.display_content = res.display_content ?? null
    } else if (chatStore.messages.length > 0) {
      // 兜底：用 id 找不到时（不该发生），覆盖第一条并同步 id
      chatStore.messages[0].content = res.content
      chatStore.messages[0].display_content = res.display_content ?? null
      chatStore.messages[0].id = res.message_id
    }
    currentGreetingIdx.value = newIdx
  } catch (err: any) {
    msg.error(err?.response?.data?.detail || '切换开场白失败')
  } finally {
    greetingSwitching.value = false
  }
}

const currentRelationship = ref<Relationship | null>(null)
const relationshipBarRef = ref<InstanceType<typeof RelationshipBar> | null>(null)

async function loadRelationship(conversationId: string) {
  try {
    const relationship = await fetchConversationRelationship(conversationId)
    if (convStore.currentId === conversationId) currentRelationship.value = relationship
  } catch {
    if (convStore.currentId === conversationId) currentRelationship.value = null
  }
}

function messagesBelongTo(conversationId: string): boolean {
  return chatStore.messages.length > 0 &&
    chatStore.messages.every((message) => message.conversation_id === conversationId)
}

async function activateConversation(conversationId: string, forgetScrollPosition: boolean) {
  chatStore.stopLiveWatch()
  currentPersonaDetail.value = null
  currentGreetingIdx.value = 0
  currentRelationship.value = null

  const reuseMessages = messagesBelongTo(conversationId)
  if (forgetScrollPosition || !reuseMessages) {
    // 主动切换对话从最新消息开始；路由离开再返回则保留原阅读位置。
    chatUi.forgetScrollPosition(conversationId)
  }

  const tasks: Promise<unknown>[] = [
    loadRelationship(conversationId),
    loadPersonaDetail(conversationId),
  ]

  // 路由往返时 store 仍持有同一对话消息，不清空即可由 MessageList 恢复滚动锚点。
  // 从首页选择另一对话进入时 currentId 已提前变化，但消息可能仍属于旧对话，必须重拉。
  if (!reuseMessages) {
    chatStore.clearMessages()
    tasks.push(chatStore.fetchMessages(conversationId).catch(() => undefined))
  }

  await Promise.all(tasks)
  if (convStore.currentId === conversationId) chatStore.startLiveWatch(conversationId)
}

watch(
  () => convStore.currentId,
  (newId) => {
    if (newId) {
      void activateConversation(newId, true)
      return
    }
    chatStore.stopLiveWatch()
    currentPersonaDetail.value = null
    currentGreetingIdx.value = 0
    currentRelationship.value = null
  },
)

onMounted(() => {
  // currentId 可能在 ChatMain 挂载前已由首页设置，或在路由往返期间保持不变；
  // 这两种情况 watcher 都不会触发，必须在挂载时补做一次激活。
  if (convStore.currentId) void activateConversation(convStore.currentId, false)
})

watch(() => convStore.relationshipChange, (change) => {
  if (change && currentRelationship.value) {
    currentRelationship.value = { ...currentRelationship.value, ...change, level_changed: true }
  }
  convStore.clearRelationshipEvents()
})

watch(() => convStore.affinityUpdate, (update) => {
  if (update && currentRelationship.value) {
    currentRelationship.value = {
      ...currentRelationship.value,
      affinity_score: update.score,
    }
    relationshipBarRef.value?.showAffinityChange(update.delta, update.reason)
  }
})

watch(() => chatStore.isStreaming, (streaming) => {
  if (!streaming && convStore.currentId) {
    loadRelationship(convStore.currentId)
  }
})

function handleSend(content: string) {
  if (!convStore.currentId) {
    msg.warning('请先创建或选择一个对话')
    return
  }
  chatStore.sendMessage(convStore.currentId, content, chatUi.replyLength)
}

// ADR-0012 卡驱动"写入对话"桥（详见模板注释）。仅在对话开启「卡界面危险能力」时挂载隐藏发送 DOM，
// 供同源消息 HTML iframe 里的卡（角色创建自动开场/快速选项）通过 `window.parent.document` 命中并自动发送。
const cardSendBridgeOn = computed(() => !!(currentConv.value as any)?.mvu_capabilities?.dangerous)
function handleCardSend() {
  if (!convStore.currentId || chatStore.isStreaming) return
  const ta = document.getElementById('send_textarea') as HTMLTextAreaElement | null
  const text = (ta?.value || '').trim()
  if (!text) return
  if (ta) ta.value = ''
  chatStore.sendMessage(convStore.currentId, text, chatUi.replyLength)
}

function handleStop() {
  chatStore.stopGeneration()
}
</script>

<style scoped>
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative; /* ADR-0008d：承载右侧卡 UI 停靠栏（absolute） */
}
.contract-stage-bar {
  margin: 0 20px 8px;
  padding: 6px 12px;
  font-size: 13px;
  color: var(--color-primary);
  background: var(--color-primary-bg);
  border-radius: 8px;
  text-align: center;
}
.mvu-init-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 20px 0;
  padding: 10px 14px;
  font-size: 13px;
  color: var(--color-text);
  background: rgba(226, 161, 95, 0.16);
  border: 1px solid rgba(226, 161, 95, 0.5);
  border-radius: 8px;
}
.mvu-init-banner span { flex: 1; }
.mvu-init-banner button {
  flex: none;
  padding: 5px 12px;
  color: #fffaf4;
  border: 0;
  border-radius: 6px;
  background: var(--accent-strong);
  font-size: 12px;
  cursor: pointer;
}
.mvu-init-banner button:disabled { opacity: 0.6; cursor: not-allowed; }
.error-bar {
  padding: 8px 16px;
  background: #e74c3c;
  color: #fff;
  font-size: 13px;
  text-align: center;
}

.config-modal-card {
  width: 520px;
  max-height: 80vh;
  overflow-y: auto;
  background: var(--color-bg-surface);
  border-radius: 12px;
  padding: 24px;
}

/* ADR-0012 卡驱动写入对话桥：主 DOM 里隐藏的 ST 等价发送 DOM（#send_textarea/#send_but），供同源
   消息 HTML iframe 的卡自动发送用。off-screen 不可见、不占观感；仍能接收卡的程序化 .click() 派发。 */
.card-send-bridge {
  position: absolute;
  left: -9999px;
  top: 0;
  width: 1px;
  height: 1px;
  overflow: hidden;
  opacity: 0;
}
</style>
