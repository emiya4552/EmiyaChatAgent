import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Conversation, Message, PersonaDetail } from '../../../types'

const state = vi.hoisted(() => ({
  convStore: {
    list: [] as Conversation[],
    currentId: null as string | null,
    currentMood: null,
    moodIntensity: null,
    milestone: null,
    relationshipChange: null,
    affinityUpdate: null,
    currentRelationship: null,
    personaAvatarUrl: vi.fn(() => null),
    clearRelationshipEvents: vi.fn(),
  },
  chatStore: {
    messages: [] as Message[],
    isStreaming: false,
    contractStage: '',
    error: null,
    fetchMessages: vi.fn(),
    clearMessages: vi.fn(),
    startLiveWatch: vi.fn(),
    stopLiveWatch: vi.fn(),
    sendMessage: vi.fn(),
    stopGeneration: vi.fn(),
  },
  chatUi: {
    openConfigSignal: 0,
    replyLength: 'medium',
    forgetScrollPosition: vi.fn(),
  },
}))

vi.mock('../../../stores/conversation', () => ({ useConversationStore: () => state.convStore }))
vi.mock('../../../stores/chat', () => ({ useChatStore: () => state.chatStore }))
vi.mock('../../../stores/chatUi', () => ({ useChatUiStore: () => state.chatUi }))

vi.mock('naive-ui', () => ({
  NModal: { name: 'NModal', template: '<div><slot /></div>' },
  useMessage: () => ({ warning: vi.fn(), success: vi.fn(), error: vi.fn() }),
}))

vi.mock('../../../api/persona', () => ({
  fetchPersonaDetail: vi.fn(),
}))

vi.mock('../../../api/relationship', () => ({
  fetchConversationRelationship: vi.fn(),
}))

vi.mock('../../../api/conversation', () => ({
  switchGreeting: vi.fn(),
  reloadMvuInitialState: vi.fn(),
}))

vi.mock('../MessageList.vue', () => ({
  default: {
    name: 'MessageList',
    props: ['messages', 'personaName', 'personaAvatarUrl', 'greetingNav'],
    template: '<div><span v-if="greetingNav" data-testid="greeting-nav">{{ greetingNav.total }}</span></div>',
  },
}))
vi.mock('../ChatInput.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../MilestoneMessage.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../ConversationConfigPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../MvuHostDock.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../../relationship/RelationshipBar.vue', () => ({ default: { template: '<div />' } }))

import ChatMain from '../ChatMain.vue'
import { fetchPersonaDetail } from '../../../api/persona'
import { fetchConversationRelationship } from '../../../api/relationship'

function conversation(id = 'conv-1'): Conversation {
  return {
    id,
    persona_id: 'persona-1',
    persona_name: '凛',
    title: '当前章节',
    user_persona_id: null,
    user_persona_name: null,
    preset_id: null,
    preset_name: null,
    chat_config: null,
    effective_chat_config: null,
    template_id: null,
    regex_preset_id: null,
    worldbook_ids: [],
    author_note: null,
    an_depth: 4,
    an_role: 'system',
    an_interval: 1,
    analyze_emotion: true,
    reply_length_enabled: true,
    variables: {},
    mvu_state: null,
    mvu_capabilities: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

function openingMessage(conversationId: string): Message {
  return {
    id: `opening-${conversationId}`,
    conversation_id: conversationId,
    role: 'assistant',
    content: '初始开场白',
    created_at: '2026-01-01T00:00:00Z',
  }
}

describe('ChatMain conversation activation', () => {
  beforeEach(() => {
    state.convStore.list = []
    state.convStore.currentId = null
    state.chatStore.messages = []
    state.chatStore.fetchMessages.mockReset().mockResolvedValue(undefined)
    state.chatStore.clearMessages.mockReset()
    state.chatStore.startLiveWatch.mockReset()
    state.chatStore.stopLiveWatch.mockReset()
    state.chatUi.forgetScrollPosition.mockReset()
    vi.clearAllMocks()
    vi.mocked(fetchPersonaDetail).mockResolvedValue({
      id: 'persona-1',
      name: '凛',
      alternate_greetings: ['第二个开场白'],
      uses_mvu: false,
    } as PersonaDetail)
    vi.mocked(fetchConversationRelationship).mockRejectedValue(new Error('尚无关系数据'))
  })

  it('restores the greeting navigator when ChatMain mounts with an already-selected conversation', async () => {
    state.convStore.list = [conversation()]
    state.convStore.currentId = 'conv-1'
    state.chatStore.messages = [openingMessage('conv-1')]

    const wrapper = shallowMount(ChatMain)
    await flushPromises()

    expect(fetchPersonaDetail).toHaveBeenCalledWith('persona-1')
    expect(state.chatStore.fetchMessages).not.toHaveBeenCalled()
    expect(state.chatUi.forgetScrollPosition).not.toHaveBeenCalled()
    expect(wrapper.findComponent({ name: 'MessageList' }).props('greetingNav')).toMatchObject({ total: 2 })
  })

  it('reloads messages when the selected conversation differs from the messages kept in the store', async () => {
    state.convStore.list = [conversation('conv-2')]
    state.convStore.currentId = 'conv-2'
    state.chatStore.messages = [openingMessage('conv-1')]

    shallowMount(ChatMain)
    await flushPromises()

    expect(state.chatStore.fetchMessages).toHaveBeenCalledWith('conv-2')
    expect(state.chatUi.forgetScrollPosition).toHaveBeenCalledWith('conv-2')
  })
})
