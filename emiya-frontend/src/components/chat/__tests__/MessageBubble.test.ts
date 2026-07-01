import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MessageBubble from '../MessageBubble.vue'
import { useAuthStore } from '../../../stores/auth'
import type { Message } from '../../../types'

vi.mock('../StreamingText.vue', () => ({
  default: {
    name: 'StreamingText',
    props: ['text', 'isStreaming'],
    template: '<div class="streaming-text">{{ text }}</div>',
  },
}))

describe('MessageBubble', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('renders the logged-in user avatar image for user messages', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: 'user-1',
      email: 'me@example.com',
      nickname: '凛',
      avatar_url: '/static/avatars/users/user-1/avatar.png',
      css_theme: null,
      created_at: '2026-01-01T00:00:00Z',
    }

    const message: Message = {
      id: 'msg-1',
      conversation_id: 'conv-1',
      role: 'user',
      content: '你好',
      created_at: '2026-01-01T00:00:00Z',
    }

    const wrapper = mount(MessageBubble, {
      props: {
        message,
        isLast: false,
        showTimestamp: false,
        personaName: 'AI',
        personaAvatarUrl: null,
      },
    })

    const avatar = wrapper.find('img.user-avatar')
    expect(avatar.exists()).toBe(true)
    expect(avatar.attributes('src')).toBe('/static/avatars/users/user-1/avatar.png')
    expect(avatar.attributes('alt')).toBe('凛')
  })
})
