<!--
  钉在副导航行左侧的"返回"按钮：teleport 到 AppNav 渲染的 #subnav-back-anchor，
  使其与副导航同级、不随正文滚动。描边幽灵样式，区别于副导航的实心激活胶囊。
  单一来源：WorkspaceHeader（角色/预设/正则/模板等）与自定义头部的页（世界书编辑）共用。
-->
<template>
  <Teleport to="#subnav-back-anchor" :disabled="!to">
    <RouterLink v-if="to" class="subnav-back" :to="to">
      <span class="subnav-back-icon" aria-hidden="true">←</span>{{ label }}
    </RouterLink>
  </Teleport>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ to?: string; label?: string }>(), { label: '返回' })
</script>

<style scoped>
.subnav-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-bg-header);
  box-shadow: var(--shadow-sm);
  font: 13px var(--font-sans);
  white-space: nowrap;
  text-decoration: none;
  transition: color var(--transition-fast), border-color var(--transition-fast), background var(--transition-fast);
}
.subnav-back:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
  background: var(--color-primary-light);
}
.subnav-back-icon { font-size: 15px; line-height: 1; }
</style>
