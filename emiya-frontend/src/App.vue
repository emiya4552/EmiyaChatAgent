<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <div v-if="safeMode" class="theme-safe-banner">
          <span>
            安全模式：已临时停用你的自定义主题。修好后去掉网址里的 <code>?safe</code> 刷新即可恢复。
          </span>
          <n-button size="tiny" tertiary @click="clearMyTheme">清空我的主题</n-button>
        </div>
        <AppNav v-if="showNav" />
        <div :class="['app-body', { 'is-chat': isChat, 'has-subnav': hasSubNav, 'is-bare': !showNav }]">
          <RouterView />
        </div>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { NConfigProvider, NMessageProvider, NDialogProvider, NButton, darkTheme, type GlobalThemeOverrides } from 'naive-ui'
import AppNav from './components/layout/AppNav.vue'
import { useThemeStore } from './stores/theme'
import { useAuthStore } from './stores/auth'
import { useUserThemeInjection, isThemeSafeMode } from './composables/useCssThemeInjection'

const route = useRoute()
const themeStore = useThemeStore()
const authStore = useAuthStore()

// 用户级全站 CSS 主题：挂在 App 根，登录态常驻、跨路由不卸载。
useUserThemeInjection()
const safeMode = isThemeSafeMode()

const AUTH_RE = /^\/(login|register|forgot-password|reset-password)/
const STUDIO_RE = /^\/(personas|worldbooks|presets|templates|regex-presets)/
const INSIGHTS_RE = /^\/(memories|mood)/

const isAuthRoute = computed(() => AUTH_RE.test(route.path))
const showNav = computed(() => !isAuthRoute.value)
const isChat = computed(() => route.path.startsWith('/chat'))
// 账户(/settings)与创作资产、记忆与感知一样有第二层副导航,需为其留出双栏高度。
// 对话(/chat)也有副导航,但由 ChatView 自管高度(.is-chat 覆盖为 padding-top:0)。
const hasSubNav = computed(
  () => STUDIO_RE.test(route.path) || INSIGHTS_RE.test(route.path) || route.path.startsWith('/settings'),
)

const isNight = computed(() => themeStore.mode === 'night')
const naiveTheme = computed(() => (isNight.value ? darkTheme : null))

// naive 表面/强调色桥接到我们的 --color-* 令牌：用户改令牌时 naive 组件(按钮/输入/卡片…)也跟着
// 换肤，避免「页面变色、naive 组件仍是硬编码 hex」的半拉子换肤。主题模式或用户 css_theme 变化后，
// 等注入落地(nextTick，getComputedStyle 会强制样式重算)再读令牌重建 overrides。
function _token(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}
const themeOverrides = ref<GlobalThemeOverrides>({})
function rebuildThemeOverrides(): void {
  themeOverrides.value = {
    common: {
      primaryColor: _token('--color-primary', '#a86252'),
      primaryColorHover: _token('--color-primary-hover', '#9c5d4e'),
      primaryColorPressed: _token('--color-primary-pressed', '#8a4f42'),
      primaryColorSuppl: _token('--color-primary-hover', '#b87363'),
      borderRadius: '8px',
      bodyColor: _token('--color-bg-page', '#f2eee7'),
      cardColor: _token('--color-bg-surface', '#fffaf2'),
      modalColor: _token('--color-bg-surface', '#fffaf2'),
      popoverColor: _token('--color-bg-elevated', '#fffaf2'),
      tableColor: _token('--color-bg-surface', '#fffaf2'),
    },
  }
}
// 同步用当前令牌初始化，避免首帧空 overrides 闪一下；后续变化经 watch 重建。
rebuildThemeOverrides()
watch(
  () => [themeStore.mode, authStore.user?.css_theme] as const,
  () => { nextTick(rebuildThemeOverrides) },
)

// 安全模式下的自救：清空用户主题并退出安全模式(去掉 ?safe 刷新到干净默认)。
async function clearMyTheme(): Promise<void> {
  try {
    await authStore.updateMe({ css_theme: '' })
  } finally {
    window.location.href = window.location.pathname
  }
}
</script>

<style>
.app-body {
  min-height: 100vh;
}
.app-body.has-subnav {
  padding-top: var(--nav-offset-sub);
}
.app-body:not(.is-chat):not(.has-subnav):not(.is-bare) {
  padding-top: var(--nav-offset);
}
/* 聊天工作区自管高度与顶部留白;认证页无导航,均不加 padding */
.app-body.is-chat,
.app-body.is-bare {
  padding-top: 0;
}

/* 主题安全模式提示条：固定在最顶层，任何页面被自定义 CSS 搞坏都能看到并一键自救。 */
.theme-safe-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 4000;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 16px;
  font-size: 13px;
  background: #b56a58;
  color: #fff;
}
.theme-safe-banner code {
  background: rgba(255, 255, 255, 0.2);
  padding: 0 4px;
  border-radius: 3px;
}
</style>
