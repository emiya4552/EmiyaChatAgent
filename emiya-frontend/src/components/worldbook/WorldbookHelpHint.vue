<template>
  <n-popover trigger="click" placement="top" :width="320">
    <template #trigger>
      <n-icon class="help-icon">
        <HelpCircleOutline />
      </n-icon>
    </template>
    <div class="help-text">
      <slot>{{ text }}</slot>
    </div>
  </n-popover>
</template>

<script setup lang="ts">
import { NPopover, NIcon } from 'naive-ui'
import { HelpCircleOutline } from '@vicons/ionicons5'

defineProps<{ text?: string }>()
</script>

<style scoped>
.help-icon {
  cursor: pointer;
  color: var(--color-text-tertiary);
  font-size: 14px;
  margin-left: 4px;
  vertical-align: middle;
  transition: color var(--transition-fast);
}
.help-icon:hover { color: var(--color-primary); }
.help-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-primary);
  white-space: normal;
}
.help-text :deep(ul) { margin: 6px 0 0; padding-left: 20px; }
.help-text :deep(li) { margin-bottom: 2px; }
.help-text :deep(code) {
  background: var(--color-bg-hover); padding: 1px 5px; border-radius: 3px;
  font-size: 12px;
}
.help-text :deep(b) { color: var(--color-text-primary); }
</style>
