import api from './index'
import type { EmotionResult, Message, WorldInfoActivated } from '../types'

// 获取对话消息（分页，按时间倒序）
export async function fetchMessages(conversationId: string, limit = 200, offset = 0): Promise<Message[]> {
  const res = await api.get(`/v1/conversations/${conversationId}/messages`, {
    params: { limit, offset },
  })
  return res.data
}

// SSE 流式发送消息
export function sendMessage(
  conversationId: string,
  content: string,
  replyLength: string,
  callbacks: {
    onToken: (token: string) => void
    onDone: (data: { message_id: string; conversation_id: string; new_memories?: number; affinity_score?: number; variables?: Record<string, unknown>; final_content?: string; final_display_content?: string; mvu_runtime_view?: unknown }) => void
    onError: (error: string, partialMessageId?: string) => void
    onEmotion?: (emotion: EmotionResult) => void
    onMemoryRecall?: (memories: Array<{ content: string; relevance: number }>) => void
    onRelationshipChange?: (data: { level: number; level_name: string; affinity_score: number }) => void
    onMilestone?: (data: { key: string; name: string }) => void
    onProfileReminder?: (data: { message: string; link: string }) => void
    onAffinityUpdate?: (data: { delta: number; reason: string; score: number }) => void
    onWorldInfoActivated?: (data: WorldInfoActivated) => void
  }
): AbortController {
  const controller = new AbortController()
  const token = localStorage.getItem('token')

  fetch(`/api/v1/conversations/${conversationId}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ content, reply_length: replyLength }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        callbacks.onError('请求失败')
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        callbacks.onError('无法读取响应流')
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          const eventMatch = part.match(/^event: (.+)$/m)
          const dataMatch = part.match(/^data: (.+)$/m)

          if (!eventMatch || !dataMatch) continue

          const event = eventMatch[1]
          try {
            const data = JSON.parse(dataMatch[1])

            if (event === 'emotion') {
              callbacks.onEmotion?.(data as EmotionResult)
            } else if (event === 'memory_recall') {
              callbacks.onMemoryRecall?.(data.memories)
            } else if (event === 'message_delta') {
              callbacks.onToken(data.content)
            } else if (event === 'message_done') {
              callbacks.onDone(data)
            } else if (event === 'error') {
              callbacks.onError(data.error || '未知错误', data.partial_message_id)
            } else if (event === 'relationship_change') {
              callbacks.onRelationshipChange?.(data)
            } else if (event === 'milestone') {
              callbacks.onMilestone?.(data)
            } else if (event === 'profile_reminder') {
              callbacks.onProfileReminder?.(data)
            } else if (event === 'affinity_update') {
              callbacks.onAffinityUpdate?.(data)
            } else if (event === 'worldinfo_activated') {
              callbacks.onWorldInfoActivated?.(data as WorldInfoActivated)
            }
          } catch {
            // 解析失败，跳过
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        callbacks.onError('网络请求失败')
      }
    })

  return controller
}

// 实时旁观 SSE — 订阅对话的 live 流（Redis PubSub 转 SSE）
export function watchLive(
  conversationId: string,
  signal: AbortSignal,
  callbacks: {
    onToken: (token: string) => void
    onDone: (data: { message_id: string; conversation_id: string; final_content?: string; final_display_content?: string; mvu_runtime_view?: unknown }) => void
    onEmotion?: (emotion: EmotionResult) => void
    onMemoryRecall?: (memories: Array<{ content: string; relevance: number }>) => void
    onError: () => void
  }
) {
  const token = localStorage.getItem('token')

  fetch(`/api/v1/conversations/${conversationId}/live`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        callbacks.onError()
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        callbacks.onError()
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const payload = JSON.parse(line.slice(6))
            // Redis PubSub 转发的格式：{"event": "...", "data": {...}}
            const event = payload.event
            const data = payload.data

            if (event === 'message_delta') {
              callbacks.onToken(data.content)
            } else if (event === 'message_done') {
              callbacks.onDone(data)
            } else if (event === 'emotion') {
              callbacks.onEmotion?.(data as EmotionResult)
            } else if (event === 'memory_recall') {
              callbacks.onMemoryRecall?.(data.memories)
            } else if (event === 'error') {
              callbacks.onError()
            }
          } catch {
            continue
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        callbacks.onError()
      }
    })
}
