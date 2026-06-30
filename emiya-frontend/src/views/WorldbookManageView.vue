<template>
  <PageShell>
    <div class="page-header">
      <n-button text @click="$router.push('/chat')">
        <template #icon><n-icon><ArrowBack /></n-icon></template>
        返回聊天
      </n-button>
      <h2 class="page-title">世界书管理</h2>
      <n-button type="primary" @click="createBlank">+ 新建</n-button>
      <n-button type="primary" @click="triggerImport">
        <template #icon><n-icon><DownloadOutline /></n-icon></template>
        导入
      </n-button>
      <input ref="fileInputRef" type="file" accept=".json" style="display: none" @change="onImportFile" />
    </div>

    <div class="page-content">
      <n-spin :show="loading">
        <div v-if="!loading && list.length === 0" class="empty-state">
          <n-empty description="暂无世界书">
            <template #extra>
              <n-button type="primary" @click="createBlank">新建世界书</n-button>
            </template>
          </n-empty>
        </div>

        <div v-else class="wb-list">
          <div
            v-for="wb in list"
            :key="wb.id"
            class="wb-card"
            @click="$router.push(`/worldbooks/${encodeURIComponent(wb.id)}/edit`)"
          >
            <div class="wb-icon">W</div>
            <div class="card-body">
              <div class="card-name-row">
                <h3 class="card-name">{{ wb.name }}</h3>
                <n-tag v-if="wb.entry_count > 0" type="success" size="small" :bordered="false">
                  {{ wb.entry_count }} 条目
                </n-tag>
                <n-tag v-else type="default" size="small" :bordered="false">空</n-tag>
                <n-tag v-if="wb.is_template" type="info" size="small" :bordered="false">系统模板</n-tag>
              </div>
              <p v-if="wb.description" class="card-desc">{{ wb.description }}</p>
              <p class="card-meta">{{ formatDate(wb.updated_at) }}</p>
            </div>
            <div class="card-actions" @click.stop>
              <n-button
                text
                type="primary"
                @click="$router.push(`/worldbooks/${encodeURIComponent(wb.id)}/edit`)"
              >编辑</n-button>
              <n-button text @click="handleExport(wb)">导出</n-button>
              <n-popconfirm v-if="!wb.is_template" @positive-click="handleDelete(wb)">
                <template #trigger>
                  <n-button text type="error">删除</n-button>
                </template>
                确定删除「{{ wb.name }}」吗？
              </n-popconfirm>
            </div>
          </div>
        </div>
      </n-spin>
    </div>
  </PageShell>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NIcon, NSpin, NEmpty, NTag, NPopconfirm, useMessage } from 'naive-ui'
import { ArrowBack, DownloadOutline } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import {
  fetchWorldbooks, deleteWorldbook, importWorldbook,
  createWorldbook, exportWorldbook,
} from '../api/worldbook'
import type { WorldbookListItem } from '../types'

const message = useMessage()
const router = useRouter()
const loading = ref(true)
const list = ref<WorldbookListItem[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

function formatDate(s: string): string {
  return new Date(s).toLocaleDateString()
}

function triggerImport() {
  fileInputRef.value?.click()
}

onMounted(async () => {
  try {
    list.value = await fetchWorldbooks()
  } catch {
    message.error('加载世界书列表失败')
  } finally {
    loading.value = false
  }
})

async function createBlank() {
  try {
    const wb = await createWorldbook({ name: '未命名世界书', entries: [] })
    router.push(`/worldbooks/${encodeURIComponent(wb.id)}/edit`)
  } catch (err: any) {
    message.error(err.response?.data?.detail || '创建失败')
  }
}

async function onImportFile(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  if (!f) return
  try {
    await importWorldbook(f)
    message.success('导入成功')
    list.value = await fetchWorldbooks()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '导入失败')
  } finally {
    input.value = ''
  }
}

async function handleExport(wb: WorldbookListItem) {
  try {
    const { filename, data } = await exportWorldbook(wb.id)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (err: any) {
    message.error(err.response?.data?.detail || '导出失败')
  }
}

async function handleDelete(wb: WorldbookListItem) {
  try {
    await deleteWorldbook(wb.id)
    list.value = list.value.filter(x => x.id !== wb.id)
    message.success(`已删除「${wb.name}」`)
  } catch (err: any) {
    message.error(err.response?.data?.detail || '删除失败')
  }
}
</script>

<style scoped>
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.page-title { flex: 1; margin: 0; font-size: 20px; white-space: nowrap; }
.page-content { min-height: 200px; }
.wb-list { display: flex; flex-direction: column; gap: 12px; }
.wb-card {
  display: flex; align-items: flex-start; background: var(--color-bg-surface); border-radius: var(--radius-md);
  padding: 20px 24px; box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}
.wb-card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }
.wb-icon {
  width: 56px; height: 56px; border-radius: var(--radius-md); flex-shrink: 0; margin-right: 16px;
  background: linear-gradient(135deg, #6b9, #4a8); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 700;
}
.card-body { flex: 1; min-width: 0; }
.card-name-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.card-name { margin: 0; font-size: 17px; font-weight: 600; }
.card-desc {
  margin: 0 0 6px; font-size: 13px; color: var(--color-text-secondary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 520px;
}
.card-meta { margin: 0; font-size: 12px; color: var(--color-text-tertiary); }
.card-actions {
  display: flex; flex-direction: column; align-items: flex-end;
  margin-left: 16px; flex-shrink: 0; gap: 2px;
}
.empty-state { padding: 60px 0; }
</style>
