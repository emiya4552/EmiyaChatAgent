<template>
  <PageShell>
    <WorkspaceHeader eyebrow="创作资产" title="世界书" description="管理可复用的世界观设定条目。">
      <template #actions>
        <n-button @click="triggerImport">
          <template #icon><n-icon><DownloadOutline /></n-icon></template>
          导入
        </n-button>
        <n-button type="primary" @click="createBlank">+ 新建世界书</n-button>
      </template>
    </WorkspaceHeader>
    <input ref="fileInputRef" type="file" accept=".json" style="display: none" @change="onImportFile" />

    <div class="page-content">
      <n-spin :show="loading">
        <div v-if="!loading && list.length === 0" class="empty-state">
          <n-empty description="暂无世界书">
            <template #extra>
              <n-button type="primary" @click="createBlank">新建世界书</n-button>
            </template>
          </n-empty>
        </div>

        <div v-else class="asset-list">
          <div
            v-for="wb in list"
            :key="wb.id"
            class="asset-card"
            @click="$router.push(`/worldbooks/${encodeURIComponent(wb.id)}/edit`)"
          >
            <div class="asset-lead wb-lead">W</div>
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
import WorkspaceHeader from '../components/layout/WorkspaceHeader.vue'
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
/* 卡片皮肤统一到全局 styles/asset-list.css；此处仅留页面专属的引导块填色与空态 */
.page-content { min-height: 200px; }
.empty-state { padding: 60px 0; }
.wb-lead { background: linear-gradient(135deg, #6b9, #4a8); }
</style>
