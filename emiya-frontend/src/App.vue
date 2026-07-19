<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <AppNav v-if="showNav" />
        <div :class="['app-body', { 'is-chat': isChat, 'has-subnav': hasSubNav, 'is-bare': !showNav }]">
          <RouterView />
        </div>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { NConfigProvider, NMessageProvider, NDialogProvider, darkTheme, type GlobalThemeOverrides } from 'naive-ui'
import AppNav from './components/layout/AppNav.vue'
import { useThemeStore } from './stores/theme'

const route = useRoute()
const themeStore = useThemeStore()

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
const themeOverrides = computed<GlobalThemeOverrides>(() => ({
  common: {
    primaryColor: isNight.value ? '#b56a58' : '#a86252',
    primaryColorHover: isNight.value ? '#c17a68' : '#9c5d4e',
    primaryColorPressed: isNight.value ? '#a85e4d' : '#8a4f42',
    primaryColorSuppl: isNight.value ? '#c17a68' : '#b87363',
    borderRadius: '8px',
    ...(isNight.value
      ? {}
      : {
          bodyColor: '#f2eee7',
          cardColor: '#fffaf2',
          modalColor: '#fffaf2',
          popoverColor: '#fffaf2',
          tableColor: '#fffaf2',
        }),
  },
}))
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
</style>
