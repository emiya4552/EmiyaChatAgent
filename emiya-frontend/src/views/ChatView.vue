<template>
  <div class="chat-layout">
    <ChatMain />
    <!-- 会话列表已上移到顶部对话副导航;此处仅挂无界面的创建弹窗宿主 -->
    <NewConversationDialog />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useConversationStore } from '../stores/conversation'
import { usePersonaThemeInjection } from '../composables/useCssThemeInjection'
import ChatMain from '../components/chat/ChatMain.vue'
import NewConversationDialog from '../components/chat/NewConversationDialog.vue'

// 角色卡级 CSS 主题注入（聊天作用域）。用户级已上移到 App 根全站注入。详见 docs/adr/0008
usePersonaThemeInjection()

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

  // 会话副导航与消息气泡共用角色图片映射，和对话列表并行加载。
  await Promise.all([
    convStore.fetchList(),
    convStore.fetchPersonaAvatars(),
  ])
})
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: 100dvh;
  padding-top: var(--chat-chrome-offset); /* 固定主栏 + 折叠态会话栏 */
  box-sizing: border-box;
  overflow: hidden;
}
</style>
