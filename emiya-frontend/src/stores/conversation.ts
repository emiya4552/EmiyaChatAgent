import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Conversation } from '../types'
import * as convApi from '../api/conversation'
import type { Relationship } from '../types'

export const useConversationStore = defineStore('conversation', () => {
  const list = ref<Conversation[]>([])
  const currentId = ref<string | null>(null)
  const loading = ref(false)

  // 当前对话的情绪氛围
  const currentMood = ref<string | null>(null)
  const moodIntensity = ref<number | null>(null)

  async function fetchList() {
    loading.value = true
    try {
      list.value = await convApi.fetchConversations()
    } finally {
      loading.value = false
    }
  }

  async function create(
    personaId: string,
    options: convApi.CreateConversationOptions = {},
  ): Promise<Conversation> {
    const conv = await convApi.createConversation(personaId, options)
    list.value.unshift(conv)
    currentId.value = conv.id
    // ADR-0015：不再加载 activeScripts
    return conv
  }

  async function deleteById(id: string) {
    await convApi.deleteConversation(id)
    list.value = list.value.filter((c) => c.id !== id)
    if (currentId.value === id) {
      currentId.value = list.value[0]?.id || null
      if (currentId.value === null) {
        // 删的是最后一个对话——清掉所有派生展示状态，避免 ChatMain 里残留旧消息
        const { useChatStore } = await import('./chat')
        useChatStore().clearMessages()
        currentMood.value = null
        moodIntensity.value = null
        recalledMemories.value = []
        activatedWorldInfo.value = []
        currentRelationship.value = null
        relationshipChange.value = null
        milestone.value = null
        affinityUpdate.value = null
      }
    }
  }

  function setCurrent(id: string) {
    currentId.value = id
    // 切换对话时重置情绪状态
    currentMood.value = null
    moodIntensity.value = null
    // 清空世界书激活集（每轮重算）
    activatedWorldInfo.value = []
    // ADR-0015：不再加载 activeScripts——reply 正则已由后端管道统一处理
  }

  function setMood(mood: string | null, intensity: number | null) {
    currentMood.value = mood
    moodIntensity.value = intensity
  }

  // 记忆召回状态
  const recalledMemories = ref<Array<{ content: string; relevance: number }>>([])

  function setRecalledMemories(memories: Array<{ content: string; relevance: number }>) {
    recalledMemories.value = memories
  }

  function clearRecalledMemories() {
    recalledMemories.value = []
  }

  // 世界书激活状态（与 memory_recall 同形态）
  const activatedWorldInfo = ref<Array<{
    uid: number
    comment: string
    worldbook_id: string
    worldbook_name: string
    position: number
  }>>([])

  function setActivatedWorldInfo(entries: Array<{
    uid: number; comment: string; worldbook_id: string;
    worldbook_name: string; position: number
  }>) {
    activatedWorldInfo.value = entries
  }

  function clearActivatedWorldInfo() {
    activatedWorldInfo.value = []
  }

  // 关系状态
  const currentRelationship = ref<Relationship | null>(null)
  const relationshipChange = ref<{ level: number; level_name: string; affinity_score: number } | null>(null)
  const milestone = ref<{ key: string; name: string } | null>(null)
  const affinityUpdate = ref<{ delta: number; reason: string; score: number } | null>(null)

  function setRelationshipChange(data: { level: number; level_name: string; affinity_score: number }) {
    relationshipChange.value = data
    if (currentRelationship.value) {
      currentRelationship.value.level = data.level
      currentRelationship.value.level_name = data.level_name
      currentRelationship.value.affinity_score = data.affinity_score
    }
  }

  function setAffinityUpdate(data: { delta: number; reason: string; score: number }) {
    affinityUpdate.value = data
    if (currentRelationship.value) {
      currentRelationship.value.affinity_score = data.score
    }
  }

  function setMilestone(data: { key: string; name: string }) {
    milestone.value = data
  }

  function clearRelationshipEvents() {
    relationshipChange.value = null
    milestone.value = null
  }

  // 每次对话提取的新记忆数量
  const newMemoriesCount = ref(0)

  function setNewMemoriesCount(count: number) {
    newMemoriesCount.value = count
  }

  return {
    list,
    currentId,
    loading,
    currentMood,
    moodIntensity,
    recalledMemories,
    setRecalledMemories,
    clearRecalledMemories,
    activatedWorldInfo,
    setActivatedWorldInfo,
    clearActivatedWorldInfo,
    currentRelationship,
    relationshipChange,
    milestone,
    affinityUpdate,
    setRelationshipChange,
    setAffinityUpdate,
    setMilestone,
    clearRelationshipEvents,
    newMemoriesCount,
    setNewMemoriesCount,
    fetchList,
    create,
    deleteById,
    setCurrent,
    setMood,
  }
})
