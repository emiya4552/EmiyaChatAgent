import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Message } from '../types'
import * as chatApi from '../api/chat'
import { useConversationStore } from './conversation'

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const isStreaming = ref(false)
  const streamingContent = ref('')
  const error = ref<string | null>(null)
  const hasMoreMessages = ref(false)

  let abortController: AbortController | null = null
  let liveAbortController: AbortController | null = null
  let liveAiMsgId: string | null = null
  let _currentPage = 0
  const _pageSize = 200

  async function fetchMessages(conversationId: string) {
    _currentPage = 0
    const msgs = await chatApi.fetchMessages(conversationId, _pageSize, 0)
    // 后端按时间倒序，前端需要正序展示
    messages.value = msgs.reverse()
    hasMoreMessages.value = msgs.length >= _pageSize
  }

  async function loadEarlierMessages(conversationId: string) {
    _currentPage++
    const offset = _currentPage * _pageSize
    const older = await chatApi.fetchMessages(conversationId, _pageSize, offset)
    if (older.length === 0) {
      hasMoreMessages.value = false
      return
    }
    // 旧消息插入到列表开头（保持正序）
    messages.value = [...older.reverse(), ...messages.value]
    hasMoreMessages.value = older.length >= _pageSize
  }

  function sendMessage(conversationId: string, content: string, replyLength: string = 'medium') {
    error.value = null
    isStreaming.value = true
    streamingContent.value = ''

    const tempId = 'temp-' + Date.now()
    messages.value.push({
      id: tempId,
      conversation_id: conversationId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    })

    const aiTempId = 'ai-temp-' + Date.now()
    messages.value.push({
      id: aiTempId,
      conversation_id: conversationId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
    })

    const convStore = useConversationStore()

    abortController = chatApi.sendMessage(conversationId, content, replyLength, {
      onToken(token) {
        streamingContent.value += token
        const aiMsg = messages.value.find((m) => m.id === aiTempId)
        if (aiMsg) {
          aiMsg.content = streamingContent.value
        }
      },
      onDone(data) {
        isStreaming.value = false
        streamingContent.value = ''
        abortController = null
        // 用后端返回的真 Message.id 替换 aiTempId；同时用 final_content 覆盖流式累积版
        // （ADR-0015：node_post_process 跑 reply 正则 + UpdateVariable 解析后落库的才是最终版）
        const aiMsg = messages.value.find((m) => m.id === aiTempId)
        if (aiMsg) {
          if (data?.message_id) aiMsg.id = data.message_id
          if (typeof data?.final_content === 'string' && data.final_content.length > 0) {
            aiMsg.content = data.final_content
          }
        }
        if (data?.new_memories) {
          convStore.setNewMemoriesCount(data.new_memories)
        }
        // 好感度更新（message_done 中携带）
        if (data?.affinity_score !== undefined && convStore.currentRelationship) {
          convStore.currentRelationship.affinity_score = data.affinity_score
        }
        // MVU v0：把后端写回后的最新 variables 同步到 store，
        // 让 ConfigPanel「对话状态变量」实时刷新（详见 ADR-0010）
        if (data?.variables !== undefined) {
          const idx = convStore.list.findIndex(c => c.id === conversationId)
          if (idx !== -1) {
            convStore.list[idx] = { ...convStore.list[idx], variables: data.variables || {} }
          }
        }
      },
      onError(err, partialMessageId) {
        error.value = err
        isStreaming.value = false
        abortController = null
        // 中断时如有 partial_message_id（已落库的不完整消息），替换 aiTempId 并补 [流式中断]
        if (partialMessageId) {
          const aiMsg = messages.value.find((m) => m.id === aiTempId)
          if (aiMsg) {
            aiMsg.id = partialMessageId
            aiMsg.content = (aiMsg.content || '') + '[流式中断]'
          }
        }
      },
      onEmotion(emotion) {
        convStore.setMood(emotion.emotion, emotion.intensity)
      },
      onMemoryRecall(memories) {
        convStore.setRecalledMemories(memories)
      },
      onRelationshipChange(data) {
        convStore.setRelationshipChange(data)
      },
      onMilestone(data) {
        convStore.setMilestone(data)
      },
      onProfileReminder(data) {
        convStore.setProfileReminder(data)
      },
      onAffinityUpdate(data) {
        convStore.setAffinityUpdate(data)
      },
      onWorldInfoActivated(data) {
        convStore.setActivatedWorldInfo(data.entries)
      },
    })
  }

  function stopGeneration() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    isStreaming.value = false
  }

  function clearMessages() {
    messages.value = []
    streamingContent.value = ''
    isStreaming.value = false
  }

  function startLiveWatch(conversationId: string) {
    stopLiveWatch()
    const convStore = useConversationStore()
    liveAbortController = new AbortController()

    chatApi.watchLive(conversationId, liveAbortController.signal, {
      onToken(token) {
        // 如果用户自己正在发消息，sendMessage 已在处理流式输出，此处的 live
        // 事件来自 Redis PubSub 广播的同一回复——跳过，避免创建重复消息。
        if (abortController) return

        if (!liveAiMsgId) {
          liveAiMsgId = 'live-' + Date.now()
          messages.value.push({
            id: liveAiMsgId,
            conversation_id: conversationId,
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString(),
          })
        }
        isStreaming.value = true
        streamingContent.value += token
        const aiMsg = messages.value.find((m) => m.id === liveAiMsgId)
        if (aiMsg) aiMsg.content = streamingContent.value
      },
      onDone(data) {
        // 如果用户自己正在发消息，不覆盖 state
        if (abortController) return
        isStreaming.value = false
        streamingContent.value = ''
        // 用真 id 替换 liveAiMsgId 消息；用 final_content 覆盖累积版（ADR-0015）
        if (liveAiMsgId) {
          const aiMsg = messages.value.find((m) => m.id === liveAiMsgId)
          if (aiMsg) {
            if (data?.message_id) aiMsg.id = data.message_id
            if (typeof data?.final_content === 'string' && data.final_content.length > 0) {
              aiMsg.content = data.final_content
            }
          }
        }
        liveAiMsgId = null
      },
      onEmotion(emotion) {
        convStore.setMood(emotion.emotion, emotion.intensity)
      },
      onMemoryRecall(memories) {
        convStore.setRecalledMemories(memories)
      },
      onError() {
        if (abortController) return
        isStreaming.value = false
        liveAiMsgId = null
      },
    })
  }

  function stopLiveWatch() {
    liveAiMsgId = null
    isStreaming.value = false
    streamingContent.value = ''
    if (liveAbortController) {
      liveAbortController.abort()
      liveAbortController = null
    }
  }

  return {
    messages,
    isStreaming,
    streamingContent,
    error,
    hasMoreMessages,
    fetchMessages,
    loadEarlierMessages,
    sendMessage,
    stopGeneration,
    clearMessages,
    startLiveWatch,
    stopLiveWatch,
  }
})
