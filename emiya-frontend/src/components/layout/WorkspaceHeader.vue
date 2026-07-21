<!-- 统一的工作区页头:eyebrow + 衬线标题 + 描述 + 右侧动作区(+可选返回链接)。 -->
<template>
  <header class="workspace-header">
    <!-- 返回按钮钉在副导航行（共享 BackButton，内部 teleport 到 #subnav-back-anchor） -->
    <BackButton :to="backTo" :label="backLabel" />
    <div class="wh-main">
      <p v-if="eyebrow" class="wh-eyebrow">{{ eyebrow }}</p>
      <h1 class="wh-title">{{ title }}</h1>
      <p v-if="description" class="wh-desc">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="wh-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
import BackButton from './BackButton.vue'

withDefaults(
  defineProps<{
    title: string
    eyebrow?: string
    description?: string
    backTo?: string
    backLabel?: string
  }>(),
  { backLabel: '返回' },
)
</script>

<style scoped>
.workspace-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 26px;
}
.wh-main {
  min-width: 0;
}
/* 返回按钮样式已移到共享组件 BackButton.vue */
.wh-eyebrow {
  margin: 0 0 8px;
  color: var(--color-eyebrow);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.wh-title {
  margin: 0;
  font: 600 34px/1.15 var(--font-serif);
  color: var(--color-text);
}
.wh-desc {
  margin: 8px 0 0;
  color: var(--color-text-secondary);
  font-size: 14px;
  line-height: 1.6;
}
.wh-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
@media (max-width: 660px) {
  .workspace-header {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }
  .wh-title {
    font-size: 27px;
  }
  .wh-actions {
    flex-wrap: wrap;
  }
}
</style>
