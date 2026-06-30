<template>
  <n-modal :show="show" @update:show="emitClose">
    <div class="modal-card">
      <h3 class="modal-title">选择 AI 人设</h3>
      <div class="persona-grid">
        <div
          v-for="p in personas"
          :key="p.id"
          class="persona-card"
          @click="select(p)"
        >
          <div class="persona-name">{{ p.name }}</div>
          <div class="persona-desc">{{ p.personality }}</div>
        </div>
      </div>

      <div class="persona-selector-footer">
        <n-button text type="primary" @click="goManage">
          管理我的自定义人设 →
        </n-button>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { NButton, NModal } from 'naive-ui'
import type { PersonaListItem } from '../../types'

defineProps<{
  show: boolean
  personas: PersonaListItem[]
}>()

const router = useRouter()

const emit = defineEmits<{
  close: []
  select: [persona: PersonaListItem]
}>()

function emitClose() {
  emit('close')
}

function select(persona: PersonaListItem) {
  emit('select', persona)
}

function goManage() {
  emitClose()
  router.push('/personas')
}
</script>

<style scoped>
.modal-card {
  width: 500px;
  max-height: 80vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 12px;
  padding: 24px;
}
.modal-title {
  margin: 0 0 16px;
  font-size: 18px;
}
.persona-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.persona-card {
  padding: 16px;
  border: 2px solid #eee;
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.persona-card:hover {
  border-color: #667eea;
}
.persona-name {
  font-size: 16px;
  font-weight: bold;
  margin-bottom: 4px;
}
.persona-desc {
  font-size: 14px;
  color: #666;
}
.persona-style {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
.persona-selector-footer {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #eee;
  text-align: center;
}
</style>
