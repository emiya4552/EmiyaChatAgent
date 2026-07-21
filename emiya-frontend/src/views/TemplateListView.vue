<template>
  <PageShell>
    <WorkspaceHeader eyebrow="创作资产" title="Prompt 模板" description="管理组装最终 Prompt 的区块模板。">
      <template #actions>
        <n-button type="primary" @click="$router.push('/templates/new')">+ 新建模板</n-button>
      </template>
    </WorkspaceHeader>

    <div class="page-content">
      <n-spin :show="loading">
        <div class="asset-list">
          <!-- 系统默认（内置）— 非 DB 行，由代码常量定义 -->
          <div class="asset-card builtin-card" @click="$router.push('/templates/default-view')">
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
            :class="['asset-card', { 'system-card': t.is_system }]"
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
import WorkspaceHeader from '../components/layout/WorkspaceHeader.vue'
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
/* 卡片皮肤统一到全局 styles/asset-list.css；此处仅留内置/系统模板的差异化描边（走令牌，适配日夜） */
.page-content { min-height: 200px; }
.asset-card.builtin-card {
  background: var(--color-primary-bg);
  border-style: dashed;
  border-color: color-mix(in srgb, var(--accent-strong) 55%, var(--color-border));
}
.asset-card.system-card {
  background: var(--color-bg-surface-2);
  border-style: dashed;
  border-color: var(--color-border);
}
</style>
