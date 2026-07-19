<template>
  <PageShell>
    <WorkspaceHeader eyebrow="创作资产" title="正则预设" description="管理对 LLM 输出做正则替换的脚本集。">
      <template #actions>
        <n-button @click="triggerImport">
          <template #icon><n-icon><DownloadOutline /></n-icon></template>
          导入
        </n-button>
        <n-button type="primary" @click="$router.push('/regex-presets/create')">+ 新建正则预设</n-button>
      </template>
    </WorkspaceHeader>
    <input ref="fileInputRef" type="file" accept=".json" style="display: none" @change="onImportFile" />

    <div class="page-content">
      <n-spin :show="loading">
        <div v-if="!loading && list.length === 0" class="empty-state">
          <n-empty description="暂无正则预设">
            <template #extra>
              <n-button type="primary" @click="$router.push('/regex-presets/create')">新建正则预设</n-button>
            </template>
          </n-empty>
        </div>

        <div v-else class="preset-list">
          <div v-for="p in list" :key="p.id" class="preset-card" @click="$router.push(`/regex-presets/${encodeURIComponent(p.id)}/edit`)">
            <div class="preset-icon">R</div>
            <div class="card-body">
              <div class="card-name-row">
                <h3 class="card-name">{{ p.name }}</h3>
                <n-tag v-if="p.script_count > 0" type="success" size="small" :bordered="false">
                  {{ p.script_count }} 条脚本
                </n-tag>
                <n-tag v-else type="default" size="small" :bordered="false">空</n-tag>
              </div>
              <p v-if="p.description" class="card-desc">{{ p.description }}</p>
              <p class="card-meta">
                {{ formatDate(p.updated_at) }}
              </p>
            </div>
            <div class="card-actions" @click.stop>
              <n-button text type="primary" @click="$router.push(`/regex-presets/${encodeURIComponent(p.id)}/edit`)">
                编辑
              </n-button>
              <n-popconfirm @positive-click="handleDelete(p)">
                <template #trigger>
                  <n-button text type="error">删除</n-button>
                </template>
                确定删除「{{ p.name }}」吗？
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
import { NButton, NIcon, NSpin, NEmpty, NTag, NPopconfirm, useMessage } from 'naive-ui'
import { ArrowBack, DownloadOutline } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import WorkspaceHeader from '../components/layout/WorkspaceHeader.vue'
import { fetchRegexPresets, deleteRegexPreset, importRegexPreset } from '../api/regexPreset'
import type { RegexPresetInfo } from '../types'

const message = useMessage()
const loading = ref(true)
const list = ref<RegexPresetInfo[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString()
}

function triggerImport() {
  fileInputRef.value?.click()
}

onMounted(async () => {
  try {
    list.value = await fetchRegexPresets()
  } catch {
    message.error('加载正则预设列表失败')
  } finally {
    loading.value = false
  }
})

async function onImportFile(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  if (!f) return
  try {
    await importRegexPreset(f)
    message.success('导入成功')
    list.value = await fetchRegexPresets()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '导入失败')
  } finally {
    input.value = ''
  }
}

async function handleDelete(p: RegexPresetInfo) {
  try {
    await deleteRegexPreset(p.id)
    list.value = list.value.filter(x => x.id !== p.id)
    message.success(`已删除「${p.name}」`)
  } catch (err: any) {
    message.error(err.response?.data?.detail || '删除失败')
  }
}
</script>

<style scoped>
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.page-title { flex: 1; margin: 0; font-size: 20px; white-space: nowrap; }
.page-content { min-height: 200px; }
.preset-list { display: flex; flex-direction: column; gap: 12px; }
.preset-card {
  display: flex; align-items: flex-start; background: var(--color-bg-surface); border-radius: var(--radius-md);
  padding: 20px 24px; box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}
.preset-card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }
.preset-icon {
  width: 56px; height: 56px; border-radius: var(--radius-md); flex-shrink: 0; margin-right: 16px;
  background: var(--color-primary); color: #fff;
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
