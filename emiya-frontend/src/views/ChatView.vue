<template>
  <div class="chat-layout">
    <ChatSidebar />
    <ChatMain />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useConversationStore } from '../stores/conversation'
import { useCssThemeInjection } from '../composables/useCssThemeInjection'
import ChatSidebar from '../components/chat/ChatSidebar.vue'
import ChatMain from '../components/chat/ChatMain.vue'

// 用户级 + 角色卡级 CSS 主题注入（详见 docs/adr/0008）
useCssThemeInjection()

const router = useRouter()
const authStore = useAuthStore()
const convStore = useConversationStore()

onMounted(async () => {
  // 初始化用户信息
  if (!authStore.user) {
    authStore.initFromStorage()
    try {
      await authStore.fetchMe()
    } catch {
      router.push('/login')
      return
    }
  }

  // 加载对话列表
  await convStore.fetchList()
})
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}
</style>
