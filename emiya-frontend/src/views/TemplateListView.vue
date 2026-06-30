<template>
  <PageShell>
    <div class="page-header">
      <n-button text @click="$router.push('/chat')">
        <template #icon><n-icon><ArrowBack /></n-icon></template>
        返回聊天
      </n-button>
      <h2 class="page-title">Prompt 模板</h2>
      <n-button type="primary" @click="$router.push('/templates/new')">新建模板</n-button>
    </div>

    <div class="page-content">
      <n-spin :show="loading">
        <div class="template-list">
          <!-- 系统默认（内置）— 非 DB 行，由代码常量定义 -->
          <div class="template-card builtin-card" @click="$router.push('/templates/default-view')">
            <div class="card-body">
              <div class="card-name-row">
                <h3 class="card-name">系统默认（内置）</h3>
                <n-tag size="tiny" type="warning">内置</n-tag>
              </div>
              <p class="card-text">{{ builtinBlockCount === null ? '加载中...' : `${builtinBlockCount} 个 Prompt 块` }}</p>
              <p class="card-desc">随版本更新；不可编辑；要个性化请复制为自己的模板</p>
            </div>
            <div class="card-actions" @click.stop>
              <n-button text type="primary" @click="$router.push('/templates/default-view')">查看</n-button>
              <n-button text :loading="duplicating" @click="onDuplicateBuiltin">复制为我的模板</n-button>
            </div>
          </div>

          <!-- 模板列表（系统模板 + 用户模板） -->
          <div
            v-for="t in templates"
            :key="t.id"
            :class="['template-card', { 'system-card': t.is_system }]"
            @click="$router.push(`/templates/${t.id}`)"
          >
            <div class="card-body">
              <div class="card-name-row">
                <h3 class="card-name">{{ t.name }}</h3>
                <n-tag v-if="t.is_system" size="tiny" type="info">系统</n-tag>
                <n-tag v-if="t.is_default" size="tiny" type="success">首选</n-tag>
              </div>
              <p class="card-text">{{ t.block_count }} 个 Prompt 块</p>
              <p v-if="t.description" class="card-desc">{{ t.description }}</p>
            </div>
            <div class="card-actions" @click.stop>
              <n-button
                text
                type="primary"
                @click="$router.push(`/templates/${t.id}`)"
              >{{ t.is_system ? '查看' : '编辑' }}</n-button>
              <n-button text @click="onDuplicate(t.id)">复制</n-button>
              <n-popconfirm v-if="!t.is_system" @positive-click="onDelete(t.id)">
                <template #trigger>
                  <n-button text type="error">删除</n-button>
                </template>
                确定删除此模板？
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
import { NButton, NIcon, NTag, NSpin, NPopconfirm, useMessage } from 'naive-ui'
import { ArrowBack } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import {
  fetchTemplates, deleteTemplate, duplicateTemplate,
  fetchDefaultPreview, createTemplate,
} from '../api/template'
import type { TemplateListItem } from '../types'

const router = useRouter()
const message = useMessage()
const loading = ref(true)
const templates = ref<TemplateListItem[]>([])
const builtinBlockCount = ref<number | null>(null)
const duplicating = ref(false)

async function load() {
  loading.value = true
  try {
    const [list, preview] = await Promise.all([
      fetchTemplates(),
      fetchDefaultPreview().catch(() => null),
    ])
    // is_default 现在表示"当前用户的首选模板"——保留并加 "首选" badge 显示
    templates.value = list
    builtinBlockCount.value = preview?.blocks.length ?? 0
  } catch {
    message.error('加载模板列表失败')
  } finally {
    loading.value = false
  }
}

async function onDuplicate(id: string) {
  try {
    await duplicateTemplate(id)
    message.success('已复制')
    await load()
  } catch {
    message.error('复制失败')
  }
}

async function onDuplicateBuiltin() {
  duplicating.value = true
  try {
    const preview = await fetchDefaultPreview()
    const created = await createTemplate({
      name: `${preview.name} (副本)`,
      description: preview.description,
      blocks: preview.blocks,
    })
    message.success('已复制为新模板')
    router.push(`/templates/${created.id}`)
  } catch {
    message.error('复制失败')
  } finally {
    duplicating.value = false
  }
}

async function onDelete(id: string) {
  try {
    await deleteTemplate(id)
    message.success('已删除')
    await load()
  } catch {
    message.error('删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}
.page-title { flex: 1; margin: 0; font-size: 20px; white-space: nowrap; }
.page-content { min-height: 200px; }
.template-list { display: flex; flex-direction: column; gap: 12px; }
.template-card {
  display: flex;
  background: var(--color-bg-surface);
  border-radius: var(--radius-md);
  padding: 20px 24px;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}
.template-card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }
.template-card.builtin-card {
  background: linear-gradient(135deg, #fefaf3, #fcf4e8);
  border: 1px dashed #e0c896;
}
.template-card.system-card {
  background: linear-gradient(135deg, #f5f9ff, #eef5ff);
  border: 1px dashed #b8d4ff;
}
.card-body { flex: 1; min-width: 0; }
.card-name-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.card-name { margin: 0; font-size: 16px; }
.card-text { margin: 0 0 2px; font-size: 14px; color: var(--color-text-secondary); }
.card-desc {
  margin: 0; font-size: 13px; color: var(--color-text-tertiary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 500px;
}
.card-actions {
  display: flex; flex-direction: column; justify-content: center; gap: 4px; margin-left: 16px;
}
</style>
