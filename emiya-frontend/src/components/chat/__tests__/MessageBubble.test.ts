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
      default_analyze_emotion: false,
      mvu_compat_enabled: true,
      output_contract_llm_detection_enabled: false,
      output_contract_llm_detection_limit: 30,
      output_contract_default_mode: 'auto',
      output_contract_allow_full_rewrite: false,
      output_contract_strict_fallback: 'repair',
      output_contract_require_confirmed: null,
      account_config: {},
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

  it('shows the output-contract badge for a repaired full_document reply', () => {
    const message: Message = {
      id: 'msg-2',
      conversation_id: 'conv-1',
      role: 'assistant',
      content: '# 第一章\n正文',
      created_at: '2026-01-01T00:00:00Z',
      output_contract: {
        contract_mode: 'full_document',
        outcome: 'passed',
        coverage: 'partial',
        method: 'reconstructed',
        requested_mode: 'repair',
        effective_mode: 'repair',
        guaranteed_rules: ['选项区块', '后台日志'],
        soft_rules: ['正文（仅 Prompt 引导）'],
      },
    }

    const wrapper = mount(MessageBubble, {
      props: {
        message,
        isLast: true,
        showTimestamp: false,
        personaName: 'AI',
        personaAvatarUrl: null,
      },
    })

    const badge = wrapper.find('.oc-badge')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toContain('格式已修复')
  })

  it('hides the badge when the contract outcome is disabled', () => {
    const message: Message = {
      id: 'msg-3',
      conversation_id: 'conv-1',
      role: 'assistant',
      content: '普通回复',
      created_at: '2026-01-01T00:00:00Z',
      output_contract: { contract_mode: 'full_document', outcome: 'disabled' },
    }

    const wrapper = mount(MessageBubble, {
      props: {
        message,
        isLast: true,
        showTimestamp: false,
        personaName: 'AI',
        personaAvatarUrl: null,
      },
    })

    expect(wrapper.find('.oc-badge').exists()).toBe(false)
  })
})
