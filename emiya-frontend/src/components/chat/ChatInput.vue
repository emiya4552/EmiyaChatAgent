<template>
  <div class="chat-input-container">
    <textarea
      v-model="inputText"
      class="input-textarea"
      placeholder="输入消息... (Enter 发送，Shift+Enter 换行)"
      rows="1"
      :disabled="isGenerating"
      @keydown="handleKeydown"
    ></textarea>
    <button
      v-if="!isGenerating"
      class="send-btn"
      :disabled="!inputText.trim()"
      @click="send"
    >
      发送
    </button>
    <button v-else class="stop-btn" @click="stop">停止</button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  isGenerating: boolean
}>()

const emit = defineEmits<{
  send: [content: string]
  stop: []
}>()

const inputText = ref('')

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function send() {
  const text = inputText.value.trim()
  if (!text || props.isGenerating) return
  emit('send', text)
  inputText.value = ''
}

function stop() {
  emit('stop')
}
</script>

<style scoped>
.chat-input-container {
  display: flex;
  gap: 10px;
  padding: 14px 28px;
  background: var(--color-bg-input);
  border-top: 1px solid var(--color-border-light);
  align-items: flex-end;
}
.input-textarea {
  flex: 1;
  resize: none;
  border: 1px solid var(--color-border);
  min-height: 46px;
  box-sizing: border-box;
  border-radius: var(--radius-md);
  padding: 11px 14px;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  outline: none;
  max-height: 120px;
}
.input-textarea:focus {
  border-color: var(--color-primary);
}
.send-btn,
.stop-btn {
  min-width: 76px;
  min-height: 46px;
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  white-space: nowrap;
}
.send-btn {
  background: var(--color-primary);
  color: #fff;
}
.send-btn:disabled {
  background: var(--color-text-placeholder);
  cursor: not-allowed;
}
.stop-btn {
  background: #e74c3c;
  color: #fff;
}

@media (max-width: 720px) {
  .chat-input-container { padding: 10px 12px; }
}
</style>
