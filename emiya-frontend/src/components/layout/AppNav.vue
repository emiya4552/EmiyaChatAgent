<!-- 全站顶部导航；聊天路由使用带上下文与可折叠会话栏的专用形态。 -->
<template>
  <ChatNavigation v-if="mainActive === 'chat'" />
  <nav v-else class="app-nav" aria-label="主导航">
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
  <nav v-if="mainActive !== 'chat' && subNav.length" class="app-subnav" aria-label="副导航">
    <RouterLink
      v-for="item in subNav"
      :key="item.label"
      class="subnav-item"
      :to="item.to"
      :class="{ active: isSubActive(item) }"
    >{{ item.label }}</RouterLink>
  </nav>
  <!-- 返回按钮的固定槽位：与副导航同一行、居左。子页（WorkspaceHeader 带 backTo）用
       <Teleport> 把返回按钮投送到这里，使其钉在副导航行、不随正文滚动。空时不可见。 -->
  <div
    v-if="mainActive !== 'chat' && subNav.length"
    id="subnav-back-anchor"
    class="subnav-back-anchor"
  ></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useThemeStore } from '../../stores/theme'
import ChatNavigation from './ChatNavigation.vue'

type SubItem = { label: string; to: string; tab?: string }

const route = useRoute()
const themeStore = useThemeStore()

const mainNav = [
  { id: 'home', label: '首页', to: '/home' },
  { id: 'chat', label: '对话', to: '/chat' },
  { id: 'studio', label: '创作资产', to: '/personas' },
  { id: 'insights', label: '记忆与感知', to: '/memories' },
  { id: 'account', label: '账户', to: '/settings' },
]

const STUDIO_RE = /^\/(personas|worldbooks|presets|templates|regex-presets)/
const INSIGHTS_RE = /^\/(memories|mood)/

const mainActive = computed(() => {
  const path = route.path
  if (path.startsWith('/home')) return 'home'
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
/* 返回按钮槽位：与副导航同一行、居左；min-height 对齐胶囊组行高使按钮垂直居中。
   实际的返回按钮由 WorkspaceHeader teleport 进来（样式在其 scoped 里，元素保留 data-v）。 */
.subnav-back-anchor {
  position: fixed;
  top: 78px;
  left: clamp(16px, 4vw, 40px);
  z-index: 199;
  display: flex;
  align-items: center;
  min-height: 42px;
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
  .app-nav {
    top: 8px;
  }
  .app-subnav {
    top: 60px;
  }
  .subnav-back-anchor {
    top: 60px;
    min-height: 36px;
  }
  .app-nav a,
  .app-subnav .subnav-item,
  .theme-toggle {
    padding: 7px 10px;
  }
}
</style>
