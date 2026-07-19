<template>
  <div class="prototype-switcher" role="navigation" aria-label="原型方案切换器">
    <button type="button" aria-label="上一个方案" @click="move(-1)">←</button>
    <span><b>{{ current }}</b> · {{ labels[current] }}</span>
    <button type="button" aria-label="下一个方案" @click="move(1)">→</button>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ current: 'A' | 'B' | 'C' }>()
const emit = defineEmits<{ change: [variant: 'A' | 'B' | 'C'] }>()

const keys = ['A', 'B', 'C'] as const
const labels = {
  A: '故事书桌',
  B: '关系轨道',
  C: '章节画布',
}
function move(direction: number) {
  const index = keys.indexOf(props.current)
  const next = keys[(index + direction + keys.length) % keys.length]
  emit('change', next)
}
</script>

<style scoped>
.prototype-switcher {
  position: fixed;
  z-index: 20;
  bottom: 20px;
  left: 50%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  color: #fff7e7;
  background: rgba(13, 17, 29, .94);
  border: 1px solid rgba(223, 177, 102, .6);
  border-radius: 999px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, .35);
  backdrop-filter: blur(14px);
  transform: translateX(-50%);
}

.prototype-switcher span { min-width: 142px; text-align: center; font-size: 13px; }
.prototype-switcher b { color: #e4b76e; }
.prototype-switcher button {
  width: 30px;
  height: 30px;
  color: inherit;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 50%;
  font-size: 20px;
}
.prototype-switcher button:hover { background: rgba(255, 255, 255, .12); }
</style>
