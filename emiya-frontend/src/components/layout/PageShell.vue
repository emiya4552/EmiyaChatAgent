<template>
  <div class="page-shell" :style="{ maxWidth }">
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ maxWidth?: string }>(), { maxWidth: '960px' })
</script>

<style scoped>
.page-shell {
  width: 100%;
  margin: 0 auto;
  padding: 8px 24px 72px;
}
@media (max-width: 660px) {
  .page-shell {
    padding: 4px 16px 56px;
  }
}
</style>
