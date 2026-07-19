<!-- PROTOTYPE — one navigable review surface; no production APIs or data mutations. -->
<template>
  <nav class="review-nav" :data-theme="theme" aria-label="原型全局导航">
    <RouterLink v-for="item in primaryNavigation" :key="item.label" :to="item.to" active-class="" exact-active-class="" :class="{ active: isPrimaryNavigationActive(item.id) }">{{ item.label }}</RouterLink>
    <button class="theme-toggle" :aria-label="theme === 'night' ? '切换到日间主题' : '切换到月间主题'" @click="toggleTheme">
      <span aria-hidden="true">{{ theme === 'night' ? '☾' : '☀' }}</span>{{ theme === 'night' ? '月' : '日' }}
    </button>
  </nav>
  <nav v-if="subNavigation.length" class="review-subnav" :data-theme="theme" :aria-label="subNavigationLabel" :data-testid="subNavigationTestId">
    <RouterLink v-for="item in subNavigation" :key="item.to" :to="item.to" active-class="" exact-active-class="" :class="{ active: isSubNavigationActive(item.to) }">{{ item.label }}</RouterLink>
  </nav>
  <div class="theme-root" :data-theme="theme">
    <RouterView v-slot="{ Component }">
      <component :is="Component" @navigate="navigate" />
    </RouterView>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createPrototypeTheme, prototypeThemeKey } from './theme'

const router = useRouter()
const route = useRoute()
const primaryNavigation = [{ id: 'home', label: '首页', to: '/' }, { id: 'chat', label: '对话', to: '/chat' }, { id: 'studio', label: '创作资产', to: '/personas' }, { id: 'insights', label: '记忆与感知', to: '/memories' }, { id: 'account', label: '账户', to: '/settings' }]
const { theme, customCss, toggleTheme } = createPrototypeTheme()
provide(prototypeThemeKey, { theme, customCss, toggleTheme })
const dayThemeCss = `
.theme-root[data-theme='day']{color:#273343;border-color:transparent;background:#edf2f7}.theme-root[data-theme='day'] .workspace{color:#273343;background:#edf2f7;--accent:#a9664f;--accent-strong:#d18b61}.theme-root[data-theme='day'] .sidebar{border-color:#c5d0da;background:#f8fafc}.theme-root[data-theme='day'] .conv{color:#4a596a}.theme-root[data-theme='day'] .conv small,.theme-root[data-theme='day'] .persona-head small,.theme-root[data-theme='day'] .perception small{color:#758497}.theme-root[data-theme='day'] .conv:hover,.theme-root[data-theme='day'] .conv.active{color:#2c3848;background:#ead7c955}.theme-root[data-theme='day'] .sidebar nav{border-color:#d7e0e8}.theme-root[data-theme='day'] .sidebar nav a{color:#58697a}.theme-root[data-theme='day'] .chat-shell{background:radial-gradient(circle at 75% 0,#dfe9f3,#f8fafc 52%)}.theme-root[data-theme='day'] .chat-header,.theme-root[data-theme='day'] .composer{border-color:#ced8e1;background:#f8fafc}.theme-root[data-theme='day'] .length,.theme-root[data-theme='day'] .icon,.theme-root[data-theme='day'] .bubble{border-color:#cdd8e2}.theme-root[data-theme='day'] .length button,.theme-root[data-theme='day'] .icon{color:#596a7a;background:#ffffff99}.theme-root[data-theme='day'] .perception{color:#596a7a;border-color:#d9e1e8}.theme-root[data-theme='day'] .bubble{background:#fff}.theme-root[data-theme='day'] .bubble small{color:#718194}.theme-root[data-theme='day'] .composer textarea{color:#263343;border-color:#c8d4df;background:#fff}.theme-root[data-theme='day'] .host-dock{color:#2c3948;border-color:#cbd6e1;background:#f8fafc}.theme-root[data-theme='day'] .host-dock span,.theme-root[data-theme='day'] .host-dock small{color:#6e7f90}
.theme-root[data-theme='day'] .settings-page{color:#253143;background:#f2eee7}.theme-root[data-theme='day'] .eyebrow{color:#997250}.theme-root[data-theme='day'] .settings-header small,.theme-root[data-theme='day'] .section-title p{color:#718093}.theme-root[data-theme='day'] .settings-nav button{color:#647182}.theme-root[data-theme='day'] .settings-nav button i{color:#9b7654}.theme-root[data-theme='day'] .settings-nav button.active{color:#2c3542;background:#e6d6c2}.theme-root[data-theme='day'] .card{border-color:#d8cfc1;background:#fffaf2;box-shadow:0 6px 18px #4a36200a}.theme-root[data-theme='day'] .card p,.theme-root[data-theme='day'] .toggle small{color:#6f7a88}.theme-root[data-theme='day'] .field{color:#536171}.theme-root[data-theme='day'] .field input,.theme-root[data-theme='day'] .field select,.theme-root[data-theme='day'] .field textarea,.theme-root[data-theme='day'] .css-theme textarea{color:#293647;border-color:#cec4b7;background:#fffefa}.theme-root[data-theme='day'] .secondary{color:#586878;border-color:#bfc5ca}.theme-root[data-theme='day'] .toggle{border-color:#e7dfd4}.theme-root[data-theme='day'] .toggle button{background:#b7bdc3}.theme-root[data-theme='day'] .toggle button.on{background:#a66554}.theme-root[data-theme='day'] .device{border-color:#e5ddd3}.theme-root[data-theme='day'] .device small,.theme-root[data-theme='day'] .device em{color:#788595}.theme-root[data-theme='day'] .notice{color:#44684e;border-color:#aac8aa;background:#edf8ed}
.theme-root[data-theme='day'] .workspace{color:#253143;background:#f2eee7;--accent:#a86252;--accent-strong:#cf9065}.theme-root[data-theme='day'] .chat-shell{background:radial-gradient(circle at 75% 0,#f4e9dc,#f2eee7 52%)}.theme-root[data-theme='day'] .chat-header,.theme-root[data-theme='day'] .composer{border-color:#d8cfc1;background:#fffaf2}.theme-root[data-theme='day'] .length,.theme-root[data-theme='day'] .icon,.theme-root[data-theme='day'] .bubble{border-color:#d8cfc1}.theme-root[data-theme='day'] .length button,.theme-root[data-theme='day'] .icon{color:#536171;background:#fffaf2}.theme-root[data-theme='day'] .perception{color:#536171;border-color:#e7dfd4}.theme-root[data-theme='day'] .bubble{background:#fffaf2}.theme-root[data-theme='day'] .bubble small,.theme-root[data-theme='day'] .persona-head small,.theme-root[data-theme='day'] .perception small{color:#718093}.theme-root[data-theme='day'] .composer textarea{color:#293647;border-color:#cec4b7;background:#fffefa}.theme-root[data-theme='day'] .conversation-tabs{border-color:#e7dfd4;background:#fffaf2}.theme-root[data-theme='day'] .conversation-tabs button{color:#536171}.theme-root[data-theme='day'] .conversation-tabs button.active{color:#2c3542;border-color:#cf906588;background:#e6d6c2}.theme-root[data-theme='day'] .conversation-tabs small{color:#788595}.theme-root[data-theme='day'] .host-dock{color:#253143;border-color:#d8cfc1;background:#fffaf2}.theme-root[data-theme='day'] .host-dock span,.theme-root[data-theme='day'] .host-dock small{color:#718093}
.theme-root[data-theme='day'] .prototype-page,.theme-root[data-theme='day'] .prototype{filter:none!important;color:#253143;background:#f2eee7}.theme-root[data-theme='day'] .story-desk,.theme-root[data-theme='day'] .orbit-home,.theme-root[data-theme='day'] .desk,.theme-root[data-theme='day'] .flow{color:#253143;background:#f2eee7}.theme-root[data-theme='day'] .hero-portrait,.theme-root[data-theme='day'] .bond-card,.theme-root[data-theme='day'] .orbit-actions>button,.theme-root[data-theme='day'] .desk-context,.theme-root[data-theme='day'] .flow-card,.theme-root[data-theme='day'] .active-chapter,.theme-root[data-theme='day'] .context-column section{color:#253143;border-color:#d8cfc1;background:#fffaf2;box-shadow:0 8px 22px #4a36200d}.theme-root[data-theme='day'] .prototype-page .intro,.theme-root[data-theme='day'] .prototype-page .chapter small,.theme-root[data-theme='day'] .prototype-page .chapter time,.theme-root[data-theme='day'] .prototype .flow-card p,.theme-root[data-theme='day'] .prototype .flow-card li,.theme-root[data-theme='day'] .prototype .desk-context p,.theme-root[data-theme='day'] .prototype .desk-context ul{color:#6f7a88}.theme-root[data-theme='day'] .prototype-page .chapter,.theme-root[data-theme='day'] .prototype .fake-form label,.theme-root[data-theme='day'] .prototype .demo-data button{color:#536171;border-color:#e7dfd4;background:#fffefa}.theme-root[data-theme='day'] .prototype-page .primary,.theme-root[data-theme='day'] .prototype .accent{color:#fffaf1;border-color:#9c5d4e;background:#a86252}.theme-root[data-theme='day'] .prototype-page .quiet,.theme-root[data-theme='day'] .prototype .coverage-list span,.theme-root[data-theme='day'] .prototype .chip-row span{color:#805f39;border-color:#cf906588;background:#fffaf2}.theme-root[data-theme='day'] .prototype-page .portrait-frame,.theme-root[data-theme='day'] .prototype-page .chapter-art,.theme-root[data-theme='day'] .prototype .chat-preview{border-color:#d8cfc1;background:#eadccf}.theme-root[data-theme='day'] .prototype .simulation-state,.theme-root[data-theme='day'] .prototype-page .prototype-note{color:#536171;border-color:#d8cfc1;background:#fffaf2}
`
let customStyleElement: HTMLStyleElement | undefined
function syncThemeStyle() {
  if (customStyleElement) customStyleElement.textContent = `${theme.value === 'day' ? dayThemeCss : ''}\n${customCss.value}`
}
onMounted(() => {
  customStyleElement = document.createElement('style')
  customStyleElement.id = 'prototype-custom-theme'
  document.head.appendChild(customStyleElement)
  syncThemeStyle()
})
onBeforeUnmount(() => customStyleElement?.remove())
watch([theme, customCss], syncThemeStyle)
function navigate(path: string) { router.push(path) }
const subNavigation = computed(() => {
  const path = route.path
  if (/^\/(personas|worldbooks|presets|templates|regex-presets)/.test(path)) return [{ label: '角色', to: '/personas' }, { label: '世界书', to: '/worldbooks' }, { label: '预设', to: '/presets' }, { label: '模板', to: '/templates' }, { label: '正则', to: '/regex-presets' }]
  if (/^\/(memories|mood|relationships)/.test(path)) return [{ label: '记忆', to: '/memories' }, { label: '情绪', to: '/mood' }, { label: '关系', to: '/relationships' }]
  if (path.startsWith('/settings')) return [{ label: '资料', to: '/settings?tab=profile' }, { label: '显示偏好', to: '/settings?tab=display' }, { label: '记忆 / 预算', to: '/settings?tab=advanced' }, { label: '安全', to: '/settings?tab=security' }, { label: '登录设备', to: '/settings?tab=sessions' }, { label: '危险区', to: '/settings?tab=danger' }]
  if (path.startsWith('/chat')) return [{ label: '会话', to: '/chat' }, { label: '新建对话', to: '/chat/new' }, { label: '对话设置', to: '/chat/settings' }, { label: '卡 UI', to: '/chat/card-ui' }]
  return []
})
const subNavigationLabel = computed(() => route.path.startsWith('/settings') ? '账户设置导航' : route.path.startsWith('/chat') ? '对话导航' : route.path.startsWith('/memories') || route.path.startsWith('/mood') || route.path.startsWith('/relationships') ? '记忆与感知导航' : '创作资产导航')
const subNavigationTestId = computed(() => /^\/(personas|worldbooks|presets|templates|regex-presets)/.test(route.path) ? 'studio-top-nav' : undefined)
function isSubNavigationActive(target: string) {
  const [path, query] = target.split('?')
  if (query) {
    const targetTab = new URLSearchParams(query).get('tab')
    const activeTab = typeof route.query.tab === 'string' ? route.query.tab : 'profile'
    return route.path === path && targetTab === activeTab
  }
  return route.path === path || route.path.startsWith(`${path}/`)
}
function isPrimaryNavigationActive(id: string) {
  const path = route.path
  if (id === 'chat') return path.startsWith('/chat')
  if (id === 'studio') return /^\/(personas|worldbooks|presets|templates|regex-presets)/.test(path)
  if (id === 'insights') return /^\/(memories|mood|relationships)/.test(path)
  if (id === 'account') return /^\/(settings|login|register|forgot-password|reset-password)/.test(path)
  return !/^\/(chat|personas|worldbooks|presets|templates|regex-presets|memories|mood|relationships|settings|login|register|forgot-password|reset-password)/.test(path)
}
</script>

<style>
.theme-root{min-height:100vh}.review-nav,.review-subnav{position:fixed;left:50%;display:flex;gap:3px;padding:5px;border-radius:999px;box-shadow:0 10px 30px #0004;backdrop-filter:blur(14px);transform:translateX(-50%)}.review-nav{z-index:100;top:14px;background:#0d111de8;border:1px solid #dfb16680}.review-subnav{z-index:99;top:78px;background:#111b29e8;border:1px solid #dfb16666}
.review-nav a,.review-subnav a{padding:7px 11px;color:#c4cbd4;border-radius:999px;font:13px Inter,"Microsoft YaHei",sans-serif;text-decoration:none;white-space:nowrap}.review-nav a.active,.review-subnav a.active{background:#e0a56e;color:#251915}@media(max-width:660px){.review-nav,.review-subnav{max-width:94vw;overflow:auto}.review-nav{top:8px}.review-subnav{top:61px}.review-nav a,.review-subnav a{padding:6px 8px}}
.theme-toggle{display:flex;align-items:center;gap:4px;padding:7px 10px;color:#e7c382;border:1px solid transparent;border-radius:999px;background:transparent;font:12px Inter,"Microsoft YaHei",sans-serif;cursor:pointer}.theme-toggle:hover{border-color:#e2b67666;background:#ffffff0b}.theme-toggle span{font-size:15px;line-height:10px}
.review-nav[data-theme='day'],.review-subnav[data-theme='day']{background:#fffaf0ed;border-color:#ba875c77;box-shadow:0 10px 30px #4a362022}.review-nav[data-theme='day'] a,.review-subnav[data-theme='day'] a{color:#526171}.review-nav[data-theme='day'] a.active,.review-subnav[data-theme='day'] a.active{background:#cf9065;color:#fffaf4}.review-nav[data-theme='day'] .theme-toggle{color:#965f39}
</style>
