<template>
  <PageShell maxWidth="800px">
    <WorkspaceHeader eyebrow="记忆与感知" title="我的记忆" description="查看、筛选并管理角色对你的长期记忆。">
      <template #actions>
        <n-popconfirm @positive-click="handleClearAll" v-if="total > 0">
          <template #trigger>
            <n-button type="error" ghost>清空全部</n-button>
          </template>
          确定清空所有记忆吗？此操作不可恢复。
        </n-popconfirm>
      </template>
    </WorkspaceHeader>

    <div class="filter-bar">
      <n-select
        v-model:value="categoryFilter"
        :options="categoryOptions"
        style="width: 140px"
        placeholder="全部分类"
        clearable
        @update:value="onFilterChange"
      />
      <n-select
        v-model:value="scopeFilter"
        :options="scopeOptions"
        style="width: 120px"
        placeholder="全部作用域"
        clearable
        @update:value="onFilterChange"
      />
      <n-select
        v-model:value="memoryTypeFilter"
        :options="memoryTypeOptions"
        style="width: 110px"
        placeholder="全部类型"
        clearable
        @update:value="onFilterChange"
      />
      <n-checkbox v-if="memories.length > 0" :checked="isAllSelected" @update:checked="toggleSelectAll">
        全选
      </n-checkbox>
    </div>

    <n-spin :show="loading">
      <div v-if="!loading && memories.length === 0" class="empty-state">
        <n-empty description="AI 还没有记住关于你的信息">
          <template #extra>
            <p class="hint">多和 AI 聊聊，它会慢慢了解你</p>
          </template>
        </n-empty>
      </div>

      <div v-else class="memory-list">
        <div v-if="selectedIds.size > 0" class="batch-bar">
          <n-button size="small" @click="selectedIds.clear()">取消选择</n-button>
          <span class="batch-count">已选 {{ selectedIds.size }} 条</span>
          <n-popconfirm @positive-click="handleBatchDelete">
            <template #trigger>
              <n-button size="small" type="error">删除选中</n-button>
            </template>
            确定删除选中的 {{ selectedIds.size }} 条记忆吗？
          </n-popconfirm>
        </div>
        <div v-for="m in memories" :key="m.id" class="memory-card" :class="{ selected: selectedIds.has(m.id) }">
          <div class="card-top">
            <div class="card-left">
              <n-checkbox :checked="selectedIds.has(m.id)" @update:checked="(v: boolean) => toggleSelect(m.id, v)" />
              <div class="card-tags">
                <n-tag :type="memoryTypeColor(m.memory_type)" size="small">{{ memoryTypeLabel(m.memory_type) }}</n-tag>
                <n-tag :type="scopeColor(m.scope)" size="small">{{ scopeLabel(m.scope) }}</n-tag>
                <n-tag :type="categoryColor(m.category)" size="small">{{ categoryLabel(m.category) }}</n-tag>
              </div>
            </div>
            <span class="importance">{{ '🔥'.repeat(Math.ceil(m.importance * 5)) }}</span>
          </div>
          <p class="card-content">{{ m.content }}</p>
          <div class="card-footer">
            <span class="card-meta">引用 {{ m.reference_count }} 次</span>
            <div class="card-actions">
              <n-button text size="small" type="primary" @click="openEdit(m)">编辑</n-button>
              <n-popconfirm @positive-click="handleDelete(m.id)">
                <template #trigger><n-button text size="small" type="error">删除</n-button></template>
                确定删除这条记忆吗？删除后不可恢复
              </n-popconfirm>
            </div>
          </div>
        </div>
      </div>

      <div v-if="total > pageSize" class="pagination">
        <n-pagination
          :page="currentPage"
          :page-size="pageSize"
          :item-count="total"
          @update:page="onPageChange"
        />
      </div>
    </n-spin>

    <MemoryEditModal
      :show="editModalShow"
      :memory="editingMemory"
      @close="editModalShow = false"
      @saved="onSaved"
    />
  </PageShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NButton, NCheckbox, NIcon, NSelect, NSpin, NEmpty, NTag, NPopconfirm, NPagination, useMessage } from 'naive-ui'
import { ArrowBack } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import WorkspaceHeader from '../components/layout/WorkspaceHeader.vue'
import { fetchMemories, deleteMemory, clearAllMemories } from '../api/memory'
import { fetchConversations } from '../api/conversation'
import type { Memory, Conversation } from '../types'
import MemoryEditModal from '../components/memory/MemoryEditModal.vue'

const message = useMessage()
const loading = ref(true)
const memories = ref<Memory[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20
const categoryFilter = ref<string | null>(null)
const scopeFilter = ref<string | null>(null)
const memoryTypeFilter = ref<string | null>(null)
const conversations = ref<Conversation[]>([])

const editModalShow = ref(false)
const editingMemory = ref<Memory | null>(null)
const selectedIds = ref(new Set<string>())

const isAllSelected = computed(() =>
  memories.value.length > 0 && memories.value.every(m => selectedIds.value.has(m.id))
)

function toggleSelect(id: string, checked: boolean) {
  if (checked) {
    selectedIds.value.add(id)
  } else {
    selectedIds.value.delete(id)
  }
  // trigger reactivity
  selectedIds.value = new Set(selectedIds.value)
}

function toggleSelectAll(checked: boolean) {
  if (checked) {
    selectedIds.value = new Set(memories.value.map(m => m.id))
  } else {
    selectedIds.value = new Set()
  }
}

async function handleBatchDelete() {
  try {
    let count = 0
    for (const id of selectedIds.value) {
      await deleteMemory(id)
      count++
    }
    selectedIds.value = new Set()
    message.success(`已删除 ${count} 条记忆`)
    loadMemories()
  } catch {
    message.error('批量删除失败')
  }
}

const categoryOptions = [
  { label: '全部', value: '' },
  { label: '基本信息', value: 'basic_info' },
  { label: '喜好偏好', value: 'preference' },
  { label: '经历事件', value: 'experience' },
  { label: '生活习惯', value: 'habit' },
  { label: '情绪模式', value: 'emotion_pattern' },
  { label: '人际关系', value: 'relationship' },
  { label: '目标愿望', value: 'goal' },
]

function categoryLabel(cat: string) {
  return categoryOptions.find(o => o.value === cat)?.label || cat
}

const scopeOptions = computed(() => {
  const base = [{ label: '全部', value: '' }]
  for (const c of conversations.value) {
    const title = c.title || `对话 ${c.id.slice(0, 8)}`
    base.push({ label: title, value: `conversation:${c.id}` })
  }
  return base
})

const memoryTypeOptions = [
  { label: '全部', value: '' },
  { label: '事实', value: 'fact' },
  { label: '事件', value: 'event' },
  { label: '状态', value: 'state' },
]

function categoryColor(cat: string) {
  const colors: Record<string, string> = {
    basic_info: 'info', preference: 'success', experience: 'warning',
    habit: 'default', emotion_pattern: 'error', relationship: 'info', goal: 'default',
  }
  return (colors[cat] || 'default') as any
}

function scopeLabel(s: string | undefined) {
  if (!s) return '未知'
  if (s.startsWith('conversation:')) {
    const convId = s.slice('conversation:'.length)
    const conv = conversations.value.find(c => c.id === convId)
    return conv ? (conv.title || `对话 ${convId.slice(0, 8)}`) : `对话 ${convId.slice(0, 8)}`
  }
  return s
}

function scopeColor(s: string | undefined) {
  return (s && s.startsWith('conversation:')) ? 'info' : 'default'
}

function memoryTypeLabel(t: string | undefined) {
  const map: Record<string, string> = { fact: '事实', event: '事件', state: '状态' }
  return map[t || ''] || t || '未知'
}

function memoryTypeColor(t: string | undefined) {
  const colors: Record<string, string> = { fact: 'success', event: 'warning', state: 'error' }
  return (colors[t || ''] || 'default') as any
}

async function loadMemories() {
  loading.value = true
  try {
    const offset = (currentPage.value - 1) * pageSize
    const scopeParam = scopeFilter.value || undefined
    const res = await fetchMemories(
      categoryFilter.value || undefined,
      scopeParam,
      memoryTypeFilter.value || undefined,
      pageSize, offset
    )
    memories.value = res.items
    total.value = res.total
  } catch {
    message.error('加载记忆列表失败')
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  currentPage.value = 1
  loadMemories()
}

function onPageChange(page: number) {
  currentPage.value = page
  loadMemories()
}

function openEdit(m: Memory) {
  editingMemory.value = m
  editModalShow.value = true
}

async function onSaved() {
  editModalShow.value = false
  await loadMemories()
}

async function handleClearAll() {
  try {
    const result = await clearAllMemories()
    message.success(`已清空 ${result.deleted} 条记忆`)
    loadMemories()
  } catch {
    message.error('清空失败')
  }
}

async function handleDelete(id: string) {
  try {
    await deleteMemory(id)
    message.success('已删除')
    await loadMemories()
  } catch {
    message.error('删除失败')
  }
}

onMounted(async () => {
  try {
    conversations.value = await fetchConversations()
  } catch { /* 非关键 */ }
  loadMemories()
})
</script>

<style scoped>
.filter-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
.memory-list { display: flex; flex-direction: column; gap: 12px; }
.memory-card { background: var(--color-bg-surface); border-radius: var(--radius-md); padding: 20px 24px; box-shadow: var(--shadow-sm); }
.memory-card.selected { border: 2px solid var(--color-primary); background: var(--color-primary-bg); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.card-left { display: flex; align-items: center; gap: 8px; }
.card-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.batch-bar { display: flex; align-items: center; gap: 12px; padding: 8px 16px; background: color-mix(in srgb, var(--accent-strong) 20%, var(--color-bg-surface)); color: var(--color-text); border-radius: 8px; margin-bottom: 8px; }
.batch-count { font-size: 14px; color: #856404; flex: 1; }
.importance { font-size: 13px; }
.card-content { margin: 0 0 8px; font-size: 15px; line-height: 1.6; }
.card-footer { display: flex; justify-content: space-between; align-items: center; }
.card-meta { font-size: 12px; color: var(--color-text-tertiary); }
.card-actions { display: flex; gap: 4px; }
.empty-state { padding: 60px 0; text-align: center; }
.hint { color: #999; font-size: 14px; }
.pagination { display: flex; justify-content: center; margin-top: 24px; }
</style>
