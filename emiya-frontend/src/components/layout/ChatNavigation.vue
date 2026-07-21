<template>
  <header class="chat-primary-bar">
    <!-- 仅在已选对话时显示当前对话身份；未选对话时左上角留空，不显示占位头像与名称 -->
    <div v-if="currentConversation" class="chat-context">
      <img
        v-if="currentPersonaAvatar"
        class="context-avatar"
        :src="currentPersonaAvatar"
        :alt="currentConversation.persona_name || 'AI'"
      />
      <span
        v-else
        class="context-avatar context-avatar-fallback"
        :style="{ background: avatarColor(currentConversation.persona_name || 'AI') }"
      >{{ (currentConversation.persona_name || 'AI')[0] }}</span>
      <span class="context-copy">
        <strong>{{ currentConversation.persona_name || 'EMIYA' }}</strong>
        <small>{{ currentConversation.title || '新对话' }}</small>
      </span>
    </div>
    <span v-else aria-hidden="true"></span>

    <nav class="primary-nav" aria-label="主导航">
      <RouterLink v-for="item in mainNav" :key="item.id" :to="item.to" :class="{ active: item.id === 'chat' }">
        {{ item.label }}
      </RouterLink>
      <button class="theme-toggle" type="button" @click="themeStore.toggle()">
        <span aria-hidden="true">{{ themeStore.mode === 'night' ? '☾' : '☀' }}</span>
        {{ themeStore.mode === 'night' ? '月' : '日' }}
      </button>
    </nav>

    <div class="primary-actions">
      <n-dropdown trigger="hover" :options="userMenuOptions" @select="handleUserMenu">
        <button type="button" class="user-menu" aria-label="用户菜单">
          <img v-if="authStore.user?.avatar_url" :src="authStore.user.avatar_url" :alt="authStore.user.nickname || '用户'" />
          <span v-else class="user-avatar-fallback" :style="{ background: avatarColor(authStore.user?.nickname || '我') }">
            {{ authStore.user?.nickname?.charAt(0) || '我' }}
          </span>
          <span class="user-name">{{ authStore.user?.nickname || '用户' }}</span>
          <n-icon class="user-caret" :size="15" aria-hidden="true"><ChevronDownOutline /></n-icon>
        </button>
      </n-dropdown>
    </div>
  </header>

  <section
    :class="['conversation-dock', { expanded: dockExpanded }]"
    aria-label="对话列表与操作"
    @mouseenter="dockHovered = true"
    @mouseleave="dockHovered = false"
    @focusin="dockFocused = true"
    @focusout="handleFocusOut"
    @keydown.esc="collapseDock"
  >
    <div class="conversation-track" @wheel="onDockWheel">
      <span v-if="conversationStore.loading && !conversationStore.list.length" class="dock-status">正在加载…</span>
      <span v-else-if="!conversationStore.list.length" class="dock-status">暂无对话</span>
      <div
        v-for="conversation in conversationStore.list"
        :key="conversation.id"
        :class="['conversation-pill', { active: conversation.id === conversationStore.currentId }]"
      >
        <button
          type="button"
          class="conversation-select"
          :aria-current="conversation.id === conversationStore.currentId ? 'page' : undefined"
          @click="conversationStore.setCurrent(conversation.id)"
        >
          <img
            v-if="conversationStore.personaAvatarUrl(conversation.persona_id)"
            class="conversation-avatar"
            :src="conversationStore.personaAvatarUrl(conversation.persona_id)!"
            :alt="conversation.persona_name || 'AI'"
          />
          <span
            v-else
            class="conversation-avatar avatar-fallback"
            :style="{ background: avatarColor(conversation.persona_name || 'AI') }"
          >{{ (conversation.persona_name || 'AI')[0] }}</span>
          <span class="conversation-title" :title="conversation.title || '新对话'">{{ conversation.title || '新对话' }}</span>
          <small>{{ relativeTime(conversation.updated_at) }}</small>
        </button>
        <n-dropdown
          trigger="click"
          :options="conversationMenuOptions"
          @select="(key: string) => handleConversationMenu(key, conversation.id, conversation.title)"
        >
          <button type="button" class="conversation-menu" :aria-label="`管理对话：${conversation.title || '新对话'}`" @click.stop>
            ···
          </button>
        </n-dropdown>
      </div>
    </div>

    <div class="dock-actions">
      <button type="button" class="dock-action" title="新建对话" aria-label="新建对话" @click="chatUi.requestNewConv()">
        <span aria-hidden="true">＋</span><span class="action-label">新建</span>
      </button>
      <button type="button" class="dock-action" title="对话设置" aria-label="对话设置" :disabled="!currentConversation" @click="chatUi.requestOpenConfig()">
        <span aria-hidden="true">⚙</span><span class="action-label">对话设置</span>
      </button>
      <!-- 回复长度：与对话设置同栏；当前模板未启用「回复长度」块时直接不显示 -->
      <div v-if="replyLengthEnabled" class="length-toggle dock-length" role="group" aria-label="回复长度">
        <button
          v-for="option in lengthOptions"
          :key="option.value"
          type="button"
          :class="{ active: chatUi.replyLength === option.value }"
          :title="option.tip"
          @click="chatUi.setReplyLength(option.value)"
        >{{ option.label }}</button>
      </div>
      <!-- 情感分析：所有对话的即时开关（ADR-0019 感知总开关） -->
      <button
        v-if="currentConversation"
        type="button"
        :class="['dock-action', { active: analyzeEmotionOn }]"
        :disabled="togglingEmotion"
        title="感知系统总开关：情绪 + 好感度。关闭后跳过回复后的上下文感知调用"
        @click="toggleAnalyzeEmotion"
      >
        <span aria-hidden="true">♡</span><span class="action-label">情感分析</span>
      </button>
      <!-- 卡界面危险能力：仅 MVU 卡 -->
      <button
        v-if="isMvuConversation"
        type="button"
        :class="['dock-action', { active: mvuDangerousOn }]"
        :disabled="togglingDangerous"
        title="ADR-0008d：允许卡界面调用 LLM 生成、修改会话楼层。默认关闭，仅对信任的卡开启（下次载卡生效）"
        @click="toggleMvuDangerous"
      >
        <span aria-hidden="true">⚠</span><span class="action-label">危险能力</span>
      </button>
      <!-- 卡 UI：仅当卡有可渲染 UI 时出现（非 MVU / 无 UI 卡直接隐藏） -->
      <button
        v-if="chatStore.mvuHostActive"
        type="button"
        :class="['dock-action', { active: chatUi.cardUiVisible }]"
        title="显示或隐藏卡 UI"
        @click="chatUi.toggleCardUi()"
      >
        <span aria-hidden="true">⌘</span><span class="action-label">卡 UI</span>
      </button>
      <button
        type="button"
        class="dock-toggle"
        :aria-expanded="dockExpanded"
        :aria-label="dockPinned ? '取消固定展开会话栏' : '固定展开会话栏'"
        :title="dockPinned ? '取消固定展开' : '固定展开会话栏'"
        @click="toggleDockPinned"
      >
        <n-icon :size="17" aria-hidden="true">
          <ChevronUpOutline v-if="dockExpanded" />
          <ChevronDownOutline v-else />
        </n-icon>
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NDropdown, NIcon, useDialog, useMessage } from 'naive-ui'
import { LogOutOutline, PersonCircleOutline, ChevronDownOutline, ChevronUpOutline } from '@vicons/ionicons5'
import { useThemeStore } from '../../stores/theme'
import { useChatUiStore } from '../../stores/chatUi'
import { useConversationStore } from '../../stores/conversation'
import { useChatStore } from '../../stores/chat'
import { useAuthStore } from '../../stores/auth'
import { avatarColor } from '../../utils/avatar'
import { updateConversationToggles, setMvuCapabilities } from '../../api/conversation'

type ReplyLength = 'short' | 'medium' | 'long'

const router = useRouter()
const themeStore = useThemeStore()
const chatUi = useChatUiStore()
const conversationStore = useConversationStore()
const chatStore = useChatStore()
const authStore = useAuthStore()
const message = useMessage()
const dialog = useDialog()

const dockHovered = ref(false)
const dockFocused = ref(false)
const dockPinned = ref(false)
const dockExpanded = computed(() => dockHovered.value || dockFocused.value || dockPinned.value)

const mainNav = [
  { id: 'home', label: '首页', to: '/home' },
  { id: 'chat', label: '对话', to: '/chat' },
  { id: 'studio', label: '创作资产', to: '/personas' },
  { id: 'insights', label: '记忆与感知', to: '/memories' },
  { id: 'account', label: '账户', to: '/settings' },
]
const lengthOptions: Array<{ value: ReplyLength; label: string; tip: string }> = [
  { value: 'short', label: '短', tip: '极简回复，1-3句话' },
  { value: 'medium', label: '中', tip: '适中回复' },
  { value: 'long', label: '长', tip: '尽情展开，详细描述' },
]
const conversationMenuOptions = [{ label: '删除对话', key: 'delete' }]
const userMenuOptions = [
  { label: '账户设置', key: 'settings', icon: () => h(NIcon, null, { default: () => h(PersonCircleOutline) }) },
  { label: '退出登录', key: 'logout', icon: () => h(NIcon, null, { default: () => h(LogOutOutline) }) },
]

const currentConversation = computed(() =>
  conversationStore.list.find((conversation) => conversation.id === conversationStore.currentId) || null,
)
const currentPersonaAvatar = computed(() =>
  conversationStore.personaAvatarUrl(currentConversation.value?.persona_id || null),
)
const replyLengthEnabled = computed(() =>
  currentConversation.value ? currentConversation.value.reply_length_enabled !== false : true,
)

// 情感分析 / 卡界面危险能力：从"对话设置"面板上移到会话操作栏的即时开关。
const analyzeEmotionOn = computed(() => currentConversation.value?.analyze_emotion !== false)
const mvuDangerousOn = computed(() => !!(currentConversation.value?.mvu_capabilities as { dangerous?: boolean } | undefined)?.dangerous)
// 是否 MVU 卡：以对话已播种的 MVU 状态判定(建对话时同步播种,initialized 即代表有 stat_data)。
const isMvuConversation = computed(() => !!currentConversation.value?.mvu_state?.initialized)
const togglingEmotion = ref(false)
const togglingDangerous = ref(false)

function patchConversation(id: string, patch: Record<string, unknown>) {
  const idx = conversationStore.list.findIndex((c) => c.id === id)
  if (idx !== -1) conversationStore.list[idx] = { ...conversationStore.list[idx], ...patch }
}

async function toggleAnalyzeEmotion() {
  const conv = currentConversation.value
  if (!conv || togglingEmotion.value) return
  togglingEmotion.value = true
  const next = !analyzeEmotionOn.value
  try {
    const updated = await updateConversationToggles(conv.id, { analyze_emotion: next })
    patchConversation(conv.id, { analyze_emotion: updated.analyze_emotion })
  } catch {
    message.error('保存失败')
  } finally {
    togglingEmotion.value = false
  }
}

async function toggleMvuDangerous() {
  const conv = currentConversation.value
  if (!conv || togglingDangerous.value) return
  togglingDangerous.value = true
  const next = !mvuDangerousOn.value
  try {
    const updated = await setMvuCapabilities(conv.id, next)
    patchConversation(conv.id, { mvu_capabilities: updated.mvu_capabilities })
    message.success(next ? '已开启卡界面危险能力（下次载卡生效）' : '已关闭卡界面危险能力')
  } catch {
    message.error('保存失败')
  } finally {
    togglingDangerous.value = false
  }
}

function relativeTime(dateStr: string): string {
  const time = new Date(dateStr).getTime()
  if (!Number.isFinite(time)) return ''
  const diff = Math.max(0, Date.now() - time)
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}天前`
  return new Date(dateStr).toLocaleDateString()
}

function handleConversationMenu(key: string, conversationId: string, title: string | null) {
  if (key !== 'delete') return
  dialog.warning({
    title: '删除对话',
    content: `确定删除「${title || '新对话'}」吗？此操作不可撤销。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await conversationStore.deleteById(conversationId)
        message.success('对话已删除')
      } catch {
        message.error('删除失败')
      }
    },
  })
}

function handleUserMenu(key: string) {
  if (key === 'logout') {
    authStore.logout()
    router.push('/login')
  } else if (key === 'settings') {
    router.push('/settings')
  }
}

function collapseDock() {
  dockPinned.value = false
  dockHovered.value = false
  dockFocused.value = false
}

function toggleDockPinned() {
  const wasPinned = dockPinned.value
  dockPinned.value = !dockPinned.value
  if (wasPinned) {
    // 点击按钮会把焦点留在栏内；解除固定时同步释放焦点，鼠标离开后才能真正折叠。
    dockFocused.value = false
    const activeElement = document.activeElement
    if (activeElement instanceof HTMLElement) activeElement.blur()
  }
}

function handleFocusOut(event: FocusEvent) {
  const dock = event.currentTarget as HTMLElement
  const next = event.relatedTarget as Node | null
  if (!next || !dock.contains(next)) dockFocused.value = false
}

// 对话条是横向滚动，但默认要 Shift+滚轮才能横滑，很多人不会用。这里把竖向滚轮
// 直接转成横向滚动。仅在"确有横向溢出 + 主要是竖向滚轮"时接管并 preventDefault，
// 其余情况放行（横向手势交给原生、无溢出时让页面正常滚动）。@wheel 默认非 passive，
// preventDefault 有效。
function onDockWheel(event: WheelEvent) {
  const el = event.currentTarget as HTMLElement | null
  if (!el) return
  if (el.scrollWidth <= el.clientWidth) return
  if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return
  // deltaMode: 0=像素(常见) / 1=行 / 2=页——非像素时按经验换算，避免滚动过慢
  const step =
    event.deltaMode === 1 ? event.deltaY * 16 :
    event.deltaMode === 2 ? event.deltaY * el.clientWidth :
    event.deltaY
  el.scrollLeft += step
  event.preventDefault()
}
</script>

<style scoped>
.chat-primary-bar {
  position: fixed;
  inset: 0 0 auto;
  z-index: 200;
  display: grid;
  height: var(--chat-primary-height);
  grid-template-columns: minmax(220px, 1fr) auto minmax(220px, 1fr);
  align-items: center;
  gap: 18px;
  padding: 8px 28px;
  box-sizing: border-box;
  border-bottom: 1px solid var(--color-border-light);
  background: color-mix(in srgb, var(--color-bg-header) 94%, transparent);
  backdrop-filter: blur(14px);
}
.chat-context,
.primary-actions,
.user-menu,
.conversation-select,
.dock-actions { display: flex; align-items: center; }
.chat-context { min-width: 0; gap: 10px; }
.context-avatar,
.conversation-avatar {
  flex: none;
  color: #fffaf4;
  border-radius: 50%;
  object-fit: cover;
}
.context-avatar { width: 40px; height: 40px; }
.context-avatar-fallback,
.avatar-fallback { display: grid; place-items: center; font-family: var(--font-serif); }
.context-copy { display: grid; min-width: 0; gap: 2px; }
.context-copy strong,
.context-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.context-copy strong { color: var(--color-text); font-size: 14px; }
.context-copy small { color: var(--color-text-secondary); font-size: 11px; }

.primary-nav {
  display: flex;
  gap: 4px;
  padding: 5px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-bg-header);
  box-shadow: var(--shadow-md);
}
.primary-nav a,
.theme-toggle {
  padding: 8px 14px;
  color: var(--color-text-secondary);
  border: 0;
  border-radius: var(--radius-pill);
  background: transparent;
  font: 13px var(--font-sans);
  white-space: nowrap;
  text-decoration: none;
  cursor: pointer;
}
.primary-nav a:hover { color: var(--color-text); }
.primary-nav a.active { color: #fffaf4; background: var(--accent-strong); }
.theme-toggle { display: flex; align-items: center; gap: 4px; color: var(--color-text-tertiary); }
.theme-toggle:hover { background: var(--color-primary-light); }

.primary-actions { justify-content: flex-end; gap: 12px; }
.length-toggle { display: flex; overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
.length-toggle.disabled { opacity: 0.42; }
.length-toggle button {
  padding: 6px 11px;
  color: var(--color-text-tertiary);
  border: 0;
  border-right: 1px solid var(--color-border);
  background: var(--color-bg-surface);
  cursor: pointer;
}
.length-toggle button:last-child { border-right: 0; }
.length-toggle button.active { color: #fffaf4; background: var(--accent-strong); }
.length-toggle button:disabled { cursor: not-allowed; }
.user-menu {
  gap: 7px;
  padding: 3px 7px 3px 3px;
  color: var(--color-text);
  border: 0;
  border-radius: var(--radius-pill);
  background: transparent;
  cursor: pointer;
}
.user-menu:hover { background: var(--color-primary-bg); }
.user-menu img,
.user-avatar-fallback { width: 30px; height: 30px; border-radius: 50%; object-fit: cover; }
.user-avatar-fallback { display: grid; place-items: center; color: #fff; }
.user-name { max-width: 90px; overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.user-caret { color: var(--color-text-tertiary); transition: color var(--transition-fast); }
.user-menu:hover .user-caret { color: var(--color-primary); }

.conversation-dock {
  position: fixed;
  top: var(--chat-primary-height);
  left: 0;
  right: 0;
  z-index: 199;
  display: flex;
  height: var(--chat-conversation-height);
  align-items: center;
  gap: 14px;
  padding: 6px 28px;
  box-sizing: border-box;
  border-bottom: 1px solid var(--color-border-light);
  background: color-mix(in srgb, var(--color-bg-header) 96%, transparent);
  box-shadow: 0 5px 16px rgba(74, 54, 32, 0.04);
  backdrop-filter: blur(14px);
  transition: height var(--transition-fast), box-shadow var(--transition-fast);
}
.conversation-dock.expanded { height: 60px; box-shadow: var(--shadow-md); }
.conversation-track {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  scrollbar-width: none;
  mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 24px), transparent 100%);
}
.conversation-track::-webkit-scrollbar { display: none; }
.dock-status { color: var(--color-text-tertiary); font-size: 12px; white-space: nowrap; }
.conversation-pill {
  display: flex;
  flex: none;
  align-items: center;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--color-bg-surface) 70%, transparent);
}
.conversation-pill:hover { color: var(--color-text); background: var(--color-primary-bg); }
.conversation-pill.active {
  color: var(--color-text);
  border-color: color-mix(in srgb, var(--accent-strong) 52%, var(--color-border));
  background: var(--color-primary-light);
}
.conversation-select { min-width: 0; gap: 7px; padding: 5px 7px; color: inherit; border: 0; background: transparent; cursor: pointer; }
.conversation-avatar { width: 25px; height: 25px; }
.conversation-title { max-width: 180px; overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.conversation-select small { color: var(--color-text-tertiary); font-size: 10px; white-space: nowrap; }
.conversation-menu {
  width: 25px;
  height: 30px;
  padding: 0 7px 2px 0;
  color: inherit;
  border: 0;
  background: transparent;
  font-weight: 700;
  cursor: pointer;
  opacity: 0;
}
.conversation-pill:hover .conversation-menu,
.conversation-pill.active .conversation-menu,
.conversation-menu:focus-visible { opacity: 1; }
.conversation-dock:not(.expanded) .conversation-pill:not(.active) { display: none; }
.conversation-dock:not(.expanded) .conversation-select small { display: none; }

.dock-actions { flex: none; gap: 7px; }
.dock-length { height: 34px; }
.dock-length button { padding: 0 10px; }
.dock-action,
.dock-toggle {
  display: flex;
  height: 34px;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 11px;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  background: var(--color-bg-surface);
  font: 12px var(--font-sans);
  white-space: nowrap;
  cursor: pointer;
}
/* 悬浮：陶土色淡填充 + 同色描边，从"静止"明确过渡到"可点"（区别于默认的浅边空心） */
.dock-action:hover:not(:disabled),
.dock-toggle:hover { color: var(--color-primary); border-color: var(--color-primary); background: var(--color-primary-light); }
/* 按下：陶土实心 + 白字 + 下沉内阴影，给明确的"已点击"触觉反馈，与悬浮的淡填充拉开层次 */
.dock-action:active:not(:disabled),
.dock-toggle:active {
  color: #fffaf4;
  border-color: var(--color-primary-pressed);
  background: var(--color-primary-pressed);
  transform: translateY(1px);
  box-shadow: inset 0 1px 3px rgba(74, 54, 32, 0.28);
}
/* 激活/开启（情感分析 / 危险能力 / 卡 UI 的开态）：实心填充，明确区别于悬浮的空心 */
.dock-action.active { color: #fffaf4; border-color: var(--accent-strong); background: var(--accent-strong); }
.dock-action.active:hover { color: #fffaf4; border-color: var(--color-primary-hover); background: var(--color-primary-hover); }
/* 开启态按下：更深的 pressed 色 + 下沉，避免与"悬浮开启态"混淆 */
.dock-action.active:active { color: #fffaf4; border-color: var(--color-primary-pressed); background: var(--color-primary-pressed); transform: translateY(1px); }
.dock-action:disabled { opacity: 0.42; cursor: not-allowed; }
.dock-toggle { width: 34px; padding: 0; font-size: 16px; }
/* 操作按钮恒为图标态（名称走 title/aria-label），不随 dock 展开变宽——避免"悬浮即位移"：
   展开只揭示左侧会话列表（flex 轨道，不推动右侧按钮），fold 的意义仍在（列表铺开 + 增高）。 */
.action-label { display: none; }
.dock-action { width: 34px; padding: 0; }

@media (max-width: 980px) {
  .chat-primary-bar { grid-template-columns: 44px minmax(0, 1fr) auto; gap: 10px; padding-inline: 14px; }
  .context-copy,
  .user-name,
  .user-menu > span:last-child { display: none; }
  .primary-nav { justify-self: center; max-width: 100%; overflow-x: auto; box-shadow: none; }
  .primary-nav a,
  .theme-toggle { padding-inline: 9px; }
  .conversation-dock { padding-inline: 14px; }
}

@media (max-width: 720px) {
  .chat-primary-bar { grid-template-columns: minmax(0, 1fr) auto; }
  .chat-context { display: none; }
  .primary-nav { justify-self: start; }
  .primary-nav a:nth-of-type(2),
  .primary-nav a:nth-of-type(3) { display: none; }
  .length-toggle button { padding-inline: 8px; }
  .user-menu { display: none; }
  .conversation-title { max-width: 42vw; }
  .conversation-select small,
  .conversation-dock .action-label { display: none; }
  .conversation-dock .dock-action { width: 34px; padding: 0; }
}
</style>
