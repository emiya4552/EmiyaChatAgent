<template>
  <n-modal :show="show" @update:show="emitClose" :mask-closable="false">
    <div class="modal-card">
      <h3 class="modal-title">选择开场白</h3>
      <p class="modal-hint">这个角色有 {{ greetings.length }} 个不同的开场白，选一个开始</p>

      <div class="greeting-list">
        <div
          v-for="(g, i) in greetings"
          :key="i"
          :class="['greeting-item', { active: selectedIndex === i }]"
          @click="selectedIndex = i"
        >
          <div class="greeting-head">
            <span class="greeting-tag">{{ i === 0 ? '默认' : `备用 #${i}` }}</span>
            <n-radio :checked="selectedIndex === i" @click.stop="selectedIndex = i" />
          </div>
          <div class="greeting-body">{{ g }}</div>
        </div>
      </div>

      <div class="modal-actions">
        <n-button @click="emitClose">取消</n-button>
        <n-button type="primary" @click="confirm">开始对话</n-button>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { NButton, NModal, NRadio } from 'naive-ui'

const props = defineProps<{
  show: boolean
  greetings: string[]
}>()

const emit = defineEmits<{
  close: []
  confirm: [index: number]
}>()

const selectedIndex = ref(0)

watch(
  () => props.show,
  (v) => {
    if (v) selectedIndex.value = 0
  },
)

function emitClose() {
  emit('close')
}

function confirm() {
  emit('confirm', selectedIndex.value)
}
</script>

<style scoped>
.modal-card {
  width: 640px;
  max-width: 90vw;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 12px;
  padding: 24px;
}
.modal-title { margin: 0 0 4px; font-size: 18px; }
.modal-hint { margin: 0 0 16px; font-size: 13px; color: #888; }

.greeting-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-right: 4px;
}
.greeting-item {
  border: 2px solid #eee;
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color 0.18s, background 0.18s;
}
.greeting-item:hover { border-color: #c8c0fb; }
.greeting-item.active { border-color: #7c5cfc; background: #faf8ff; }

.greeting-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.greeting-tag {
  font-size: 12px;
  color: #7c5cfc;
  background: #f0eaff;
  border-radius: 999px;
  padding: 2px 10px;
}
.greeting-body {
  font-size: 14px;
  line-height: 1.6;
  color: #333;
  white-space: pre-wrap;
  max-height: 240px;
  overflow-y: auto;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 18px;
}
</style>
