<template>
  <div class="milestone-msg" v-if="visible">
    <div class="milestone-content">
      <span class="milestone-icon">{{ icon }}</span>
      <span class="milestone-text">{{ text }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'

interface Props {
  event: { key: string; name: string } | null
}

const props = defineProps<Props>()
const visible = ref(false)
const text = ref('')
const icon = ref('')

let timer: ReturnType<typeof setTimeout> | null = null

const milestoneMessages: Record<string, { icon: string; text: string }> = {
  first_deep_talk: { icon: '💬', text: '第一次深度对话 — 你们更了解彼此了' },
  first_vulnerability: { icon: '💝', text: '第一次袒露心事 — 信任正在建立' },
  first_joke: { icon: '😄', text: '第一次开玩笑 — 气氛变得更轻松了' },
  consecutive_days_7: { icon: '📅', text: '连续聊了 7 天 — 习惯彼此的存在' },
  message_100: { icon: '💯', text: '第 100 条消息 — 这段关系在成长' },
  message_500: { icon: '🌟', text: '第 500 条消息 — 你们真的很聊得来' },
  penetration_30: { icon: '🔮', text: '深度对话达 30 次 — 已是知心好友' },
}

watch(() => props.event, (evt) => {
  if (!evt) return
  const msg = milestoneMessages[evt.key]
  if (msg) {
    icon.value = msg.icon
    text.value = msg.text
  } else {
    icon.value = '🎉'
    text.value = evt.name
  }
  visible.value = true
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { visible.value = false }, 5000)
})

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<style scoped>
.milestone-msg {
  display: flex;
  justify-content: center;
  padding: 8px 16px;
  animation: milestoneFadeIn 0.4s ease;
}
.milestone-content {
  background: linear-gradient(135deg, #e8f5e9, #e3f2fd);
  border-radius: 16px;
  padding: 8px 18px;
  font-size: 13px;
  color: #333;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.milestone-icon {
  margin-right: 6px;
}
@keyframes milestoneFadeIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
