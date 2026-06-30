import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock api/chat 必须在 import store 之前
vi.mock('../../api/chat', () => ({
  sendMessage: vi.fn(),
  watchLive: vi.fn(),
  fetchMessages: vi.fn(),
}))

import { useChatStore } from '../chat'
import * as chatApi from '../../api/chat'

describe('useChatStore.sendMessage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('B1: onDone 用真 message_id 替换 aiTempId', () => {
    const store = useChatStore()
    let capturedCallbacks: any = null
    ;(chatApi.sendMessage as any).mockImplementation(
      (_convId: string, _content: string, _replyLen: string, callbacks: any) => {
        capturedCallbacks = callbacks
        return new AbortController()
      }
    )

    store.sendMessage('conv-1', '你好', 'short')

    // 两条临时消息已 push
    expect(store.messages.length).toBe(2)
    const userMsg = store.messages[0]
    const aiMsg = store.messages[1]
    expect(userMsg.role).toBe('user')
    expect(aiMsg.role).toBe('assistant')
    expect(aiMsg.id.startsWith('ai-temp-')).toBe(true)
    const originalAiTempId = aiMsg.id

    // 模拟 token 流
    capturedCallbacks.onToken('你')
    capturedCallbacks.onToken('好')
    expect(store.messages[1].content).toBe('你好')

    // 模拟 onDone 带真 id
    capturedCallbacks.onDone({
      message_id: 'real-uuid-1',
      conversation_id: 'conv-1',
      new_memories: 0,
    })

    // ai 消息 id 应替换为真 id
    expect(store.messages[1].id).toBe('real-uuid-1')
    expect(store.messages[1].id).not.toBe(originalAiTempId)
    expect(store.isStreaming).toBe(false)
  })

  it('B2: onError 带 partial_message_id 时替换 id 并追加 [流式中断]', () => {
    const store = useChatStore()
    let capturedCallbacks: any = null
    ;(chatApi.sendMessage as any).mockImplementation(
      (_convId: string, _content: string, _replyLen: string, callbacks: any) => {
        capturedCallbacks = callbacks
        return new AbortController()
      }
    )

    store.sendMessage('conv-1', '你好', 'short')
    const originalAiTempId = store.messages[1].id

    // 流式中累积了部分 token
    capturedCallbacks.onToken('你')
    capturedCallbacks.onToken('好')
    expect(store.messages[1].content).toBe('你好')

    // 中断 — error 携带 partial_message_id
    capturedCallbacks.onError('生成中断，请稍后重试', 'partial-uuid-1')

    expect(store.messages[1].id).toBe('partial-uuid-1')
    expect(store.messages[1].id).not.toBe(originalAiTempId)
    expect(store.messages[1].content).toBe('你好[流式中断]')
    expect(store.isStreaming).toBe(false)
    expect(store.error).toBe('生成中断，请稍后重试')
  })

  it('B3: watchLive onDone 用真 message_id 替换 liveAiMsgId', () => {
    const store = useChatStore()
    let capturedCallbacks: any = null
    ;(chatApi.watchLive as any).mockImplementation(
      (_convId: string, _signal: any, callbacks: any) => {
        capturedCallbacks = callbacks
      }
    )

    store.startLiveWatch('conv-1')

    // 旁观流：第一个 token 时动态创建 liveAiMsgId 消息
    capturedCallbacks.onToken('你')
    expect(store.messages.length).toBe(1)
    const liveAiMsg = store.messages[0]
    expect(liveAiMsg.role).toBe('assistant')
    expect(liveAiMsg.id.startsWith('live-')).toBe(true)
    const originalLiveId = liveAiMsg.id

    capturedCallbacks.onToken('好')
    expect(store.messages[0].content).toBe('你好')

    // 旁观流的 onDone 也带真 id（Redis 转发的同一份 msg_done_data）
    capturedCallbacks.onDone({
      message_id: 'live-real-uuid-1',
      conversation_id: 'conv-1',
    })

    expect(store.messages[0].id).toBe('live-real-uuid-1')
    expect(store.messages[0].id).not.toBe(originalLiveId)
    expect(store.isStreaming).toBe(false)
  })

  it('B2-补: onError 无 partialMessageId 时不替换 id 也不补后缀', () => {
    const store = useChatStore()
    let capturedCallbacks: any = null
    ;(chatApi.sendMessage as any).mockImplementation(
      (_convId: string, _content: string, _replyLen: string, callbacks: any) => {
        capturedCallbacks = callbacks
        return new AbortController()
      }
    )

    store.sendMessage('conv-1', '你好', 'short')
    const originalAiTempId = store.messages[1].id

    // 流一个 token 都没出来就 error
    capturedCallbacks.onError('请求失败')

    expect(store.messages[1].id).toBe(originalAiTempId)
    expect(store.messages[1].content).toBe('')
    expect(store.error).toBe('请求失败')
  })
})
