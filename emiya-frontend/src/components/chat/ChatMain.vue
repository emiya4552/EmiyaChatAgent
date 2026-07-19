<template>
  <div class="chat-main">
    <div class="chat-header">
      <div class="header-left" v-if="currentConv">
        <img
          v-if="personaAvatarUrl"
          class="persona-avatar"
          :src="personaAvatarUrl!"
          :alt="currentConv.persona_name || 'AI'"
        />
        <div v-else class="persona-avatar" :style="{ background: avatarColor(currentConv.persona_name || 'AI') }">
          {{ (currentConv.persona_name || 'AI')[0] }}
        </div>
        <span class="persona-name">{{ currentConv.persona_name || '未选择人设' }}</span>
        <span class="separator">|</span>
        <span class="conv-title">{{ currentConv.title || '新对话' }}</span>
      </div>
      <div class="header-left" v-else>
        <span class="welcome-text">选择一个对话或新建一个开始聊天</span>
      </div>

      <div class="header-right">
        <div
          :class="['length-toggle', { disabled: !replyLengthEnabled }]"
          :title="!replyLengthEnabled ? '当前模板未启用「回复长度」块；去模板编辑器开启后此控件才生效' : ''"
        >
          <button
            v-for="opt in lengthOptions"
            :key="opt.value"
            :class="['length-btn', { active: replyLength === opt.value }]"
            :title="opt.tip"
            :disabled="!replyLengthEnabled"
            @click="setReplyLength(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
        <n-button v-if="currentConv" size="small" @click="showConfigPanel = true">
          <template #icon><n-icon><SettingsOutline /></n-icon></template>
        </n-button>
        <n-dropdown trigger="hover" :options="userMenuOptions" @select="handleUserMenu">
          <span class="user-info">
            <img
              v-if="authStore.user?.avatar_url"
              :src="authStore.user.avatar_url"
              :alt="authStore.user.nickname || '用户'"
              class="user-avatar user-avatar-img"
            />
            <span
              v-else
              class="user-avatar"
              :style="{ background: avatarColor(authStore.user?.nickname || '我') }"
            >
              {{ authStore.user?.nickname?.charAt(0) || '我' }}
            </span>
            <span class="user-name">{{ authStore.user?.nickname || '用户' }}</span>
          </span>
        </n-dropdown>
      </div>
    </div>

    <div v-if="perceptionOn && convStore.currentMood" class="mood-indicator">
      <span class="mood-emoji">{{ moodEmoji }}</span>
      <span class="mood-label">{{ convStore.currentMood }}</span>
      <span class="mood-intensity">· 强度 {{ convStore.moodIntensity }}/10</span>
    </div>

    <RelationshipBar
      v-if="currentConv && perceptionOn"
      ref="relationshipBarRef"
      :relationship="currentRelationship"
      :persona-name="currentConv.persona_name || ''"
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
import { computed, ref, watch, h, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useConversationStore } from '../../stores/conversation'
import { useChatStore } from '../../stores/chat'
import { useAuthStore } from '../../stores/auth'
import { NIcon, NDropdown, NButton, NModal, useMessage } from 'naive-ui'
import { LogOutOutline, SettingsOutline, PersonCircleOutline } from '@vicons/ionicons5'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'
import RelationshipBar from '../relationship/RelationshipBar.vue'
import MilestoneMessage from './MilestoneMessage.vue'
import ConversationConfigPanel from './ConversationConfigPanel.vue'
import MvuHostDock from './MvuHostDock.vue'
import { fetchConversationRelationship } from '../../api/relationship'
import { fetchPersonas, fetchPersonaDetail } from '../../api/persona'
import { switchGreeting } from '../../api/conversation'
import { avatarColor } from '../../utils/avatar'
import type { Relationship, PersonaListItem, PersonaDetail } from '../../types'

const router = useRouter()
const convStore = useConversationStore()
const chatStore = useChatStore()

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
const authStore = useAuthStore()
const msg = useMessage()

const showConfigPanel = ref(false)

const REPLY_LENGTH_KEY = 'emiya_reply_length'
const lengthOptions = [
  { value: 'short', label: '短', tip: '极简回复，1-3句话' },
  { value: 'medium', label: '中', tip: '适中回复' },
  { value: 'long', label: '长', tip: '尽情展开，详细描述' },
]
const replyLength = ref(localStorage.getItem(REPLY_LENGTH_KEY) || 'medium')

function setReplyLength(v: string) {
  replyLength.value = v
  localStorage.setItem(REPLY_LENGTH_KEY, v)
}

const currentConv = computed(() =>
  convStore.list.find((c) => c.id === convStore.currentId) || null
)

// 感知系统开关（ADR-0020）：对话级 analyze_emotion 显式为 false 时，隐藏对话内的
// mood/关系条/里程碑指示器。必须显式判 !== false —— 历史开过感知的对话 DB 里已存
// current_mood/relationship 数据，只靠"有没有数据"判断会在关闭后仍露出指示器。
const perceptionOn = computed(() => currentConv.value?.analyze_emotion !== false)

// 当前对话使用的模板里 reply_length block 是否启用——derived 字段，由后端
// _compute_reply_length_enabled 查模板算好（详见 ADR-0014）。
// 未选对话时按"已启用"处理（让按钮可点，避免选了对话前没法预设长度偏好）。
const replyLengthEnabled = computed(() =>
  currentConv.value ? currentConv.value.reply_length_enabled !== false : true
)

const personas = ref<PersonaListItem[]>([])
const personaAvatarUrl = computed(() => {
  if (!currentConv.value?.persona_id) return null
  const p = personas.value.find(p => p.id === currentConv.value!.persona_id)
  return p?.avatar_url || null
})

onMounted(async () => {
  try { personas.value = await fetchPersonas('all') } catch { /* */ }
})

// ─── 开场白左右切换（ADR-0017）──────────────────────────────────
// 切对话时拉 personaDetail 拿 alternate_greetings；当 messages 里只有
// 一条且是 assistant（即用户还没回复过）时，给 MessageList 传 greetingNav。
const currentPersonaDetail = ref<PersonaDetail | null>(null)
const currentGreetingIdx = ref(0)
const greetingSwitching = ref(false)

async function loadCurrentPersonaDetail() {
  const personaId = currentConv.value?.persona_id
  if (!personaId) { currentPersonaDetail.value = null; return }
  try {
    currentPersonaDetail.value = await fetchPersonaDetail(personaId)
  } catch {
    currentPersonaDetail.value = null
  }
  // 切对话总是把 idx 重置为 0；后端 create_conversation 默认就是 first_message
  currentGreetingIdx.value = 0
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

const MOOD_EMOJI_MAP: Record<string, string> = {
  '开心': '😊', '平静': '😌', '低落': '😔', '焦虑': '😰', '愤怒': '😤',
  '兴奋': '🤩', '疲惫': '😴', '困惑': '🤔', '感动': '🥹', '思念': '💭',
}
const moodEmoji = computed(() => MOOD_EMOJI_MAP[convStore.currentMood || ''] || '😌')

const userMenuOptions = [
  {
    label: '账户设置',
    key: 'settings',
    icon: () => h(NIcon, null, { default: () => h(PersonCircleOutline) }),
  },
  {
    label: '退出登录',
    key: 'logout',
    icon: () => h(NIcon, null, { default: () => h(LogOutOutline) }),
  },
]

const currentRelationship = ref<Relationship | null>(null)
const relationshipBarRef = ref<InstanceType<typeof RelationshipBar> | null>(null)

function handleUserMenu(key: string) {
  if (key === 'logout') {
    authStore.logout()
    router.push('/login')
  } else if (key === 'settings') {
    router.push('/settings')
  }
}

async function loadRelationship() {
  if (!convStore.currentId) return
  try {
    currentRelationship.value = await fetchConversationRelationship(convStore.currentId)
  } catch {
    currentRelationship.value = null
  }
}

watch(
  () => convStore.currentId,
  async (newId) => {
    chatStore.stopLiveWatch()
    // 切对话清掉本地 persona detail / greetingIdx，避免上个对话的开场白列表错配
    currentPersonaDetail.value = null
    currentGreetingIdx.value = 0
    if (newId) {
      chatStore.clearMessages()
      try {
        await chatStore.fetchMessages(newId)
      } catch {
        // ignore
      }
      loadRelationship()
      // ADR-0017：拉 persona 详情，用 alternate_greetings 决定 navigator 是否显示
      loadCurrentPersonaDetail()
      chatStore.startLiveWatch(newId)
    }
  }
)

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
    loadRelationship()
  }
})

function handleSend(content: string) {
  if (!convStore.currentId) {
    msg.warning('请先创建或选择一个对话')
    return
  }
  chatStore.sendMessage(convStore.currentId, content, replyLength.value)
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
  chatStore.sendMessage(convStore.currentId, text, replyLength.value)
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
.chat-header {
  padding: 10px 20px;
  background: var(--color-bg-header);
  border-bottom: 1px solid var(--color-border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.persona-avatar {
  width: 28px; height: 28px;
  border-radius: 50%;
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600;
  flex-shrink: 0;
  object-fit: cover;
}
.persona-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
}
.separator {
  color: var(--color-border);
}
.conv-title {
  font-size: 14px;
  color: var(--color-text-secondary);
}
.welcome-text {
  color: var(--color-text-tertiary);
  font-size: 14px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}
.user-info:hover {
  background: var(--color-border-light);
}
.user-avatar {
  width: 28px; height: 28px;
  border-radius: 50%;
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600;
}
.user-avatar-img { object-fit: cover; }
.user-name {
  font-size: 14px;
  color: var(--color-text);
}

.mood-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 20px;
  background: var(--color-bg-page);
  border-bottom: 1px solid var(--color-border-light);
  font-size: 13px;
  color: var(--color-text-secondary);
  transition: all var(--transition-normal);
}
.mood-emoji { font-size: 15px; }
.mood-label { font-weight: 500; }
.mood-intensity { color: var(--color-text-tertiary); }

.length-toggle {
  display: flex;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.length-toggle.disabled {
  opacity: 0.4;
}
.length-btn {
  padding: 4px 14px;
  border: none;
  background: var(--color-bg-surface);
  color: var(--color-text-tertiary);
  font-size: 13px;
  cursor: pointer;
  transition: all var(--transition-fast);
  border-right: 1px solid var(--color-border);
}
.length-btn:last-child { border-right: none; }
.length-btn:not(:disabled):hover { background: var(--color-primary-bg); color: var(--color-primary); }
.length-btn.active { background: var(--color-primary); color: #fff; }
.length-btn:disabled { cursor: not-allowed; }

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
