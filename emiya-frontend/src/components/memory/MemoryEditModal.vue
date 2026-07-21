<template>
  <n-modal :show="show" @update:show="$emit('close')">
    <div class="modal-card">
      <h3>编辑记忆</h3>
      <n-form label-placement="top">
        <n-form-item label="内容">
          <n-input
            v-model:value="form.content"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
          />
        </n-form-item>
        <n-form-item label="分类">
          <n-select v-model:value="form.category" :options="categoryOptions" />
        </n-form-item>
        <n-form-item label="作用域">
          <n-select v-model:value="form.scope" :options="scopeOptions" />
        </n-form-item>
        <n-form-item label="类型">
          <n-select v-model:value="form.memory_type" :options="memoryTypeOptions" />
        </n-form-item>
      </n-form>
      <div class="modal-actions">
        <n-button @click="$emit('close')">取消</n-button>
        <n-button type="primary" :loading="saving" @click="handleSave">保存</n-button>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { NModal, NForm, NFormItem, NInput, NSelect, NButton, useMessage } from 'naive-ui'
import { updateMemory } from '../../api/memory'
import type { Memory } from '../../types'

const props = defineProps<{ show: boolean; memory: Memory | null }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const msg = useMessage()
const saving = ref(false)

const form = ref({ content: '', category: 'basic_info', scope: 'global', memory_type: 'fact' })

const categoryOptions = [
  { label: '基本信息', value: 'basic_info' },
  { label: '喜好偏好', value: 'preference' },
  { label: '经历事件', value: 'experience' },
  { label: '生活习惯', value: 'habit' },
  { label: '情绪模式', value: 'emotion_pattern' },
  { label: '人际关系', value: 'relationship' },
  { label: '目标愿望', value: 'goal' },
]

const scopeOptions = ref<Array<{ label: string; value: string }>>([
  { label: '全局', value: 'global' },
])

watch(() => props.memory, (m) => {
  if (m) {
    form.value.content = m.content
    form.value.category = m.category
    form.value.scope = m.scope || 'global'
    form.value.memory_type = m.memory_type || 'fact'
    // 动态添加 persona scope 选项
    if (m.scope && m.scope.startsWith('persona:') && !scopeOptions.value.find(o => o.value === m.scope)) {
      scopeOptions.value.push({ label: `人设专属 (${m.scope})`, value: m.scope })
    }
  }
})

const memoryTypeOptions = [
  { label: '事实', value: 'fact' },
  { label: '事件', value: 'event' },
  { label: '状态', value: 'state' },
]

async function handleSave() {
  if (!props.memory) return
  saving.value = true
  try {
    await updateMemory(props.memory.id, {
      content: form.value.content,
      category: form.value.category,
      scope: form.value.scope,
      memory_type: form.value.memory_type,
    })
    msg.success('已保存')
    emit('saved')
  } catch {
    msg.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.modal-card { width: 480px; max-height: 80vh; background: var(--color-bg-surface); border-radius: 12px; padding: 24px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 20px; }
</style>
