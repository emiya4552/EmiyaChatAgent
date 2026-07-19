import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 顶部对话副导航 → 聊天区动作的信号桥。
 * 会话副导航把每个具体对话做成胶囊(点选=切换,读/写 conversation store 即可),
 * 唯独"新建对话"需要触发 NewConversationDialog 的创建弹窗——它与导航分属不同组件,
 * 用自增信号(而非布尔)让"再点一次"也能重复触发。
 */
export const useChatUiStore = defineStore('chatUi', () => {
  const newConvSignal = ref(0)

  return {
    newConvSignal,
    requestNewConv: () => { newConvSignal.value++ },
  }
})
