<!-- 全站两层顶部胶囊导航(替代旧的深色左侧栏区块导航)。 -->
<template>
  <nav class="app-nav" aria-label="主导航">
    <RouterLink
      v-for="item in mainNav"
      :key="item.id"
      :to="item.to"
      :class="{ active: mainActive === item.id }"
    >{{ item.label }}</RouterLink>
    <button
      class="theme-toggle"
      type="button"
      :aria-label="themeStore.mode === 'night' ? '切换到日间主题' : '切换到夜间主题'"
      @click="themeStore.toggle()"
    >
      <span aria-hidden="true">{{ themeStore.mode === 'night' ? '☾' : '☀' }}</span>
      {{ themeStore.mode === 'night' ? '月' : '日' }}
    </button>
  </nav>
  <nav
    v-if="mainActive === 'chat'"
    class="app-subnav conversation-subnav"
    aria-label="对话列表"
  >
    <button
      type="button"
      class="subnav-item new-conversation-button"
      @click="chatUi.requestNewConv()"
    >＋ 新建对话</button>

    <span v-if="conversationStore.loading && !conversationStore.list.length" class="conversation-status">
      正在加载…
    </span>
    <span v-else-if="!conversationStore.list.length" class="conversation-status">
      暂无对话
    </span>

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
        <span
          class="conversation-avatar"
          :style="{ background: avatarColor(conversation.persona_name || 'AI') }"
          aria-hidden="true"
        >{{ (conversation.persona_name || 'AI')[0] }}</span>
        <span class="conversation-copy">
          <span class="conversation-title" :title="conversation.title || '新对话'">
            {{ conversation.title || '新对话' }}
          </span>
          <small>{{ conversation.persona_name || '未设人设' }} · {{ relativeTime(conversation.updated_at) }}</small>
        </span>
      </button>
      <n-dropdown
        trigger="click"
        :options="conversationMenuOptions"
        @select="(key: string) => handleConversationMenu(key, conversation.id)"
      >
        <button
          type="button"
          class="conversation-menu"
          :aria-label="`管理对话：${conversation.title || '新对话'}`"
          title="对话操作"
          @click.stop
        >···</button>
      </n-dropdown>
    </div>
  </nav>
  <nav v-else-if="subNav.length" class="app-subnav" aria-label="副导航">
    <RouterLink
      v-for="item in subNav"
      :key="item.label"
      class="subnav-item"
      :to="item.to"
      :class="{ active: isSubActive(item) }"
    >{{ item.label }}</RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { NDropdown, useMessage } from 'naive-ui'
import { useThemeStore } from '../../stores/theme'
import { useChatUiStore } from '../../stores/chatUi'
import { useConversationStore } from '../../stores/conversation'
import { avatarColor } from '../../utils/avatar'

type SubItem = { label: string; to: string; tab?: string }

const route = useRoute()
const themeStore = useThemeStore()
const chatUi = useChatUiStore()
const conversationStore = useConversationStore()
const message = useMessage()

const conversationMenuOptions = [
  { label: '删除对话', key: 'delete' },
]

const mainNav = [
  { id: 'chat', label: '对话', to: '/chat' },
  { id: 'studio', label: '创作资产', to: '/personas' },
  { id: 'insights', label: '记忆与感知', to: '/memories' },
  { id: 'account', label: '账户', to: '/settings' },
]

const STUDIO_RE = /^\/(personas|worldbooks|presets|templates|regex-presets)/
const INSIGHTS_RE = /^\/(memories|mood)/

const mainActive = computed(() => {
  const path = route.path
  if (path.startsWith('/chat')) return 'chat'
  if (STUDIO_RE.test(path)) return 'studio'
  if (INSIGHTS_RE.test(path)) return 'insights'
  if (path.startsWith('/settings')) return 'account'
  return ''
})

const subNav = computed<SubItem[]>(() => {
  switch (mainActive.value) {
    case 'studio':
      return [
        { label: '角色', to: '/personas' },
        { label: '世界书', to: '/worldbooks' },
        { label: '预设', to: '/presets' },
        { label: '模板', to: '/templates' },
        { label: '正则', to: '/regex-presets' },
      ]
    case 'insights':
      return [
        { label: '记忆', to: '/memories' },
        { label: '情绪', to: '/mood' },
      ]
    case 'account':
      return [
        { label: '资料', to: '/settings?tab=profile', tab: 'profile' },
        { label: '显示偏好', to: '/settings?tab=display', tab: 'display' },
        { label: '记忆 / 预算', to: '/settings?tab=advanced', tab: 'advanced' },
        { label: '安全', to: '/settings?tab=security', tab: 'security' },
        { label: '登录设备', to: '/settings?tab=sessions', tab: 'sessions' },
        { label: '危险区', to: '/settings?tab=danger', tab: 'danger' },
      ]
    default:
      return []
  }
})

function relativeTime(dateStr: string): string {
  const time = new Date(dateStr).getTime()
  if (!Number.isFinite(time)) return ''
  const diff = Math.max(0, Date.now() - time)
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins}分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}天前`
  return new Date(dateStr).toLocaleDateString()
}

async function handleConversationMenu(key: string, conversationId: string) {
  if (key !== 'delete') return
  try {
    await conversationStore.deleteById(conversationId)
    message.success('对话已删除')
  } catch {
    message.error('删除失败')
  }
}

function isSubActive(item: SubItem) {
  if (item.tab) {
    const active = typeof route.query.tab === 'string' ? route.query.tab : 'profile'
    return route.path === '/settings' && active === item.tab
  }
  const path = item.to.split('?')[0]
  return route.path === path || route.path.startsWith(`${path}/`)
}
</script>

<style scoped>
.app-nav,
.app-subnav {
  position: fixed;
  left: 50%;
  z-index: 200;
  display: flex;
  gap: 4px;
  padding: 5px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-bg-header);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(12px);
  transform: translateX(-50%);
}
.app-nav {
  top: 14px;
}
.app-subnav {
  top: 78px;
  z-index: 199;
}
.conversation-subnav {
  width: min(1180px, calc(100vw - 32px));
  justify-content: flex-start;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
}

.app-nav a,
.app-subnav .subnav-item,
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
  transition: color var(--transition-fast), background var(--transition-fast);
}
.app-nav a:hover,
.app-subnav .subnav-item:hover {
  color: var(--color-text);
}
.app-nav a.active,
.app-subnav .subnav-item.active {
  color: #fffaf4;
  background: var(--accent-strong);
}
.new-conversation-button {
  flex: none;
}
.conversation-status {
  align-self: center;
  padding: 0 10px;
  color: var(--color-text-tertiary);
  font-size: 12px;
  white-space: nowrap;
}
.conversation-pill {
  display: flex;
  flex: none;
  align-items: center;
  color: var(--color-text-secondary);
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  background: transparent;
  transition: color var(--transition-fast), border-color var(--transition-fast), background var(--transition-fast);
}
.conversation-pill:hover {
  color: var(--color-text);
  background: var(--color-primary-bg);
}
.conversation-pill.active {
  color: var(--color-text);
  border-color: color-mix(in srgb, var(--accent-strong) 52%, transparent);
  background: var(--color-primary-light);
}
.conversation-select {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
  padding: 4px 4px 4px 5px;
  color: inherit;
  border: 0;
  background: transparent;
  cursor: pointer;
}
.conversation-avatar {
  display: grid;
  width: 25px;
  height: 25px;
  flex: none;
  place-items: center;
  color: #fffaf4;
  border-radius: 50%;
  font: 600 11px var(--font-serif);
}
.conversation-copy {
  display: grid;
  min-width: 0;
  gap: 1px;
  text-align: left;
}
.conversation-title {
  max-width: 170px;
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conversation-copy small {
  max-width: 170px;
  overflow: hidden;
  color: var(--color-text-tertiary);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conversation-menu {
  display: grid;
  width: 26px;
  height: 30px;
  flex: none;
  place-items: center;
  padding: 0 7px 2px 1px;
  color: inherit;
  border: 0;
  border-radius: 0 var(--radius-pill) var(--radius-pill) 0;
  background: transparent;
  font-weight: 700;
  cursor: pointer;
}
.conversation-menu:hover {
  color: var(--color-primary);
}
.theme-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}
.theme-toggle:hover {
  background: var(--color-primary-light);
}
.theme-toggle span {
  font-size: 15px;
  line-height: 1;
}

@media (max-width: 660px) {
  .app-nav,
  .app-subnav {
    max-width: 94vw;
    overflow-x: auto;
  }
  .conversation-subnav {
    width: 94vw;
  }
  .app-nav {
    top: 8px;
  }
  .app-subnav {
    top: 60px;
  }
  .app-nav a,
  .app-subnav .subnav-item,
  .theme-toggle {
    padding: 7px 10px;
  }
}
</style>
