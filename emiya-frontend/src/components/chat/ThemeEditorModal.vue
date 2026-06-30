<template>
  <n-modal :show="show" @update:show="emitClose" :mask-closable="false">
    <div class="modal-card">
      <h3 class="modal-title">用户级 CSS 主题</h3>
      <p class="modal-hint">
        这里写的 CSS 对所有对话生效；角色卡自带的样式（卡作者写的）在 Persona 编辑页里改。
        卡作者的样式会在用户样式之后注入（CSS cascade，Persona 覆盖 User）。
      </p>

      <n-input
        v-model:value="css"
        type="textarea"
        :autosize="{ minRows: 14, maxRows: 28 }"
        placeholder="/* 示例：状态栏样式
StatusBlock {
  display: block;
  background: #f7f5ff;
  padding: 10px;
  border-radius: 8px;
} */"
        class="css-input"
      />

      <div class="modal-actions">
        <n-button @click="emitClose">取消</n-button>
        <n-button v-if="hasCss" type="error" @click="clear">清空</n-button>
        <n-button type="primary" :loading="saving" @click="save">保存</n-button>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { NButton, NInput, NModal, useMessage } from 'naive-ui'
import { useAuthStore } from '../../stores/auth'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ close: [] }>()

const authStore = useAuthStore()
const message = useMessage()

const css = ref<string>('')
const saving = ref(false)

const hasCss = computed(() => !!(authStore.user?.css_theme || '').trim())

watch(
  () => props.show,
  (v) => {
    if (v) css.value = authStore.user?.css_theme || ''
  },
)

function emitClose() {
  emit('close')
}

async function save() {
  saving.value = true
  try {
    await authStore.updateMe({ css_theme: css.value })
    message.success('主题已保存')
    emit('close')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function clear() {
  saving.value = true
  try {
    await authStore.updateMe({ css_theme: '' })
    css.value = ''
    message.success('主题已清空')
    emit('close')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '清空失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.modal-card {
  width: 720px;
  max-width: 92vw;
  max-height: 86vh;
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  display: flex;
  flex-direction: column;
}
.modal-title { margin: 0 0 8px; font-size: 18px; }
.modal-hint {
  margin: 0 0 16px;
  font-size: 12px;
  color: #888;
  line-height: 1.6;
}
.css-input :deep(textarea) {
  font-family: 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
}
</style>
