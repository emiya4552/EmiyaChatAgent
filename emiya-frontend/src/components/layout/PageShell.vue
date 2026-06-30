<template>
  <div class="page-shell" :style="{ maxWidth: maxWidth }">
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ maxWidth?: string }>(), { maxWidth: '780px' })
</script>

<style scoped>
.page-shell {
  margin: 0 auto;
  padding: 24px;
  min-height: 100vh;
  background: var(--color-bg-page);
}
</style>
