<template>
  <PageShell>
    <div class="page-header">
      <n-button text @click="$router.push('/chat')">
        <template #icon><n-icon><ArrowBack /></n-icon></template>
        返回聊天
      </n-button>
      <h2 class="page-title">角色卡管理</h2>
      <n-button type="primary" @click="showImport = true">
        <template #icon><n-icon><DownloadOutline /></n-icon></template>
        导入角色卡
      </n-button>
      <n-button
        type="primary"
        :disabled="customCount >= 50"
        @click="$router.push('/personas/create')"
      >
        + 新建
      </n-button>
    </div>

    <div class="page-content">
      <n-spin :show="loading">
        <div v-if="!loading && personas.length === 0" class="empty-state">
          <n-empty description="暂无角色卡" />
        </div>

        <div v-else class="persona-list">
          <div v-for="p in personas" :key="p.id" class="persona-card" @click="$router.push(`/personas/${p.id}`)">
            <div class="card-left">
              <div v-if="p.avatar_url" class="card-avatar" :style="{ backgroundImage: `url(${p.avatar_url})` }" />
              <div v-else class="card-avatar-placeholder" :style="{ background: avatarColor(p.name) }">{{ p.name[0] }}</div>
            </div>
            <div class="card-body">
              <div class="card-name-row">
                <h3 class="card-name">{{ p.name }}</h3>
                <n-tag v-if="p.is_template" size="tiny" type="warning">预设</n-tag>
                <n-tag v-if="p.is_owner" size="tiny" type="info">我的</n-tag>
              </div>
              <p class="card-text">{{ p.personality }}</p>
              <div v-if="p.tags?.length" class="card-tags">
                <n-tag v-for="t in p.tags.slice(0, 4)" :key="t" size="tiny" type="success">{{ t }}</n-tag>
              </div>
            </div>
            <div class="card-actions" @click.stop>
              <n-button text type="primary" @click="$router.push(`/personas/${p.id}/edit`)">编辑</n-button>
              <n-popconfirm @positive-click="handleDelete(p)">
                <template #trigger>
                  <n-button text type="error">删除</n-button>
                </template>
                确定删除「{{ p.name }}」吗？关联的对话、消息、情绪记录和记忆将全部删除，不可恢复。
              </n-popconfirm>
            </div>
          </div>

          <p v-if="customCount >= 50" class="limit-hint">已达上限（50 个），无法再创建新的角色卡</p>
        </div>
      </n-spin>
    </div>

    <!-- 导入对话框 -->
    <n-modal v-model:show="showImport" preset="card" title="导入角色卡" style="max-width: 520px;">
      <n-tabs v-model:value="importTab" type="line" animated>
        <n-tab-pane name="png" tab="PNG 文件">
          <n-upload
            :default-upload="false"
            accept=".png,.json"
            @change="onUploadChange"
            :show-file-list="true"
          >
            <n-upload-dragger>
              <n-icon size="48"><CloudUploadOutline /></n-icon>
              <p>拖拽 PNG 角色卡到此处，或点击选择</p>
              <p class="hint">支持 .png 和 .json 格式</p>
            </n-upload-dragger>
          </n-upload>
        </n-tab-pane>
        <n-tab-pane name="url" tab="URL 链接">
          <n-space vertical>
            <n-input v-model:value="importUrl" placeholder="https://chub.ai/characters/..." />
            <n-button type="primary" :loading="parsingUrl" @click="onImportUrl">解析 URL</n-button>
          </n-space>
        </n-tab-pane>
      </n-tabs>

      <n-divider />

      <n-spin :show="parsing">
        <div v-if="parseError" class="parse-error">
          <n-alert type="error">{{ parseError }}</n-alert>
        </div>
        <div v-if="parseResult && !parseError" class="parse-preview">
          <div class="preview-header">
            <div v-if="parseResult.avatar_preview" class="preview-avatar" :style="{ backgroundImage: `url(${parseResult.avatar_preview})` }" />
            <div>
              <h4>{{ parseResult.preview.name }}</h4>
              <p class="preview-meta">
                {{ parseResult.source_format }}
                <template v-if="parseResult.preview.tags?.length">
                  · {{ parseResult.preview.tags.join('、') }}
                </template>
              </p>
              <p v-if="parseResult.duplicate_check.is_duplicate" class="dup-warn">
                注意：{{ parseResult.duplicate_check.similar_persona?.name }} 已存在
              </p>
            </div>
          </div>
          <n-alert
            v-if="parseResult.preview.uses_mvu"
            type="info"
            :show-icon="true"
            class="mvu-banner"
          >
            <template #header>已识别为 MVU 卡，将启用兼容模式</template>
            EMIYA 已检测到此角色卡使用 MVU 系统。导入后将自动：
            <ul class="mvu-banner-list">
              <li>解析 LLM 输出末尾的 <code>&lt;UpdateVariable&gt;</code> 指令并写回对话级变量</li>
              <li>展开世界书 / 角色卡中的 <code>&lt;%_ if %&gt;</code> 条件块（基于当前变量求值）</li>
            </ul>
            <p class="mvu-banner-note">
              当前 v0 暂不支持楼层快照 / 回滚 / Zod schema 校验（计划 v1）。详见 ADR-0010。
            </p>
          </n-alert>
          <n-divider />
          <n-form label-placement="top" size="small">
            <n-form-item label="性格">
              <n-input v-model:value="parseResult.preview.personality" type="textarea" :rows="2" />
            </n-form-item>
            <n-form-item label="背景">
              <n-input v-model:value="parseResult.preview.background" type="textarea" :rows="2" />
            </n-form-item>
            <n-form-item label="开场白">
              <n-input v-model:value="parseResult.preview.first_message" type="textarea" :rows="2" />
            </n-form-item>
          </n-form>
        </div>
      </n-spin>

      <template #footer>
        <n-button @click="showImport = false; parseResult = null; parseError = ''">取消</n-button>
        <n-button type="primary" :disabled="!parseResult" :loading="importing" @click="onConfirmImport">确认导入</n-button>
      </template>
    </n-modal>
  </PageShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  NButton, NIcon, NSpin, NEmpty, NPopconfirm, NTag, NModal, NTabs, NTabPane,
  NUpload, NUploadDragger, NInput, NSpace, NDivider, NForm, NFormItem, NAlert,
  useMessage,
} from 'naive-ui'
import { ArrowBack, DownloadOutline, CloudUploadOutline } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import { avatarColor } from '../utils/avatar'
import { fetchPersonas, deletePersona, importParse, importConfirm } from '../api/persona'
import type { PersonaListItem, ImportParseResult } from '../types'

const message = useMessage()
const loading = ref(true)
const personas = ref<PersonaListItem[]>([])
const allPersonas = ref<PersonaListItem[]>([])

const customCount = computed(() =>
  allPersonas.value.filter(p => !p.is_template && p.is_owner).length
)

onMounted(async () => {
  try {
    allPersonas.value = await fetchPersonas('all')
    personas.value = allPersonas.value
  } catch {
    message.error('加载角色卡列表失败')
  } finally {
    loading.value = false
  }
})

async function handleDelete(p: PersonaListItem) {
  try {
    const result = await deletePersona(p.id)
    allPersonas.value = allPersonas.value.filter(x => x.id !== p.id)
    personas.value = personas.value.filter(x => x.id !== p.id)
    const parts: string[] = []
    if (result.affected_conversations > 0) parts.push(`${result.affected_conversations} 个对话`)
    if (result.affected_memories > 0) parts.push(`${result.affected_memories} 条记忆`)
    const extra = parts.length > 0 ? `，同时清除了 ${parts.join('、')}` : ''
    message.success(`已删除「${p.name}」${extra}`)
  } catch (err: any) {
    message.error(err.response?.data?.detail || '删除失败')
  }
}

// ─── 导入 ───

const showImport = ref(false)
const importTab = ref('png')
const importUrl = ref('')
const parsing = ref(false)
const parsingUrl = ref(false)
const importing = ref(false)
const parseResult = ref<ImportParseResult | null>(null)
const parseError = ref('')
const importFile = ref<File | null>(null)

async function onUploadChange(data: { file: any; fileList: any[]; event?: Event }) {
  const f = data.file?.file as File | null
  if (!f) return
  importFile.value = f
  parseError.value = ''
  parseResult.value = null
  parsing.value = true
  try {
    const fd = new FormData()
    fd.append('file', importFile.value)
    parseResult.value = await importParse(fd)
  } catch (err: any) {
    parseError.value = err.response?.data?.detail || '解析失败，请确认文件是有效的角色卡'
  } finally {
    parsing.value = false
  }
}

async function onImportUrl() {
  if (!importUrl.value.trim()) return
  parsingUrl.value = true
  parseError.value = ''
  parseResult.value = null
  try {
    const fd = new FormData()
    fd.append('url', importUrl.value)
    parseResult.value = await importParse(fd)
  } catch (err: any) {
    parseError.value = err.response?.data?.detail || 'URL 解析失败'
  } finally {
    parsingUrl.value = false
  }
}

async function onConfirmImport() {
  if (!parseResult.value) return
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('parse_result', JSON.stringify(parseResult.value.preview))
    fd.append('overrides', JSON.stringify(parseResult.value.preview))
    if (importFile.value && importTab.value === 'png') {
      fd.append('avatar_file', importFile.value)
    }
    const result = await importConfirm(fd)
    // 刷新列表
    allPersonas.value = await fetchPersonas('all')
    personas.value = allPersonas.value
    message.success(`已导入「${result.persona.name}」`)
    showImport.value = false
    parseResult.value = null
    importFile.value = null
  } catch (err: any) {
    message.error(err.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}
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
.persona-list { display: flex; flex-direction: column; gap: 12px; }
.persona-card {
  display: flex;
  background: var(--color-bg-surface);
  border-radius: var(--radius-md);
  padding: 20px 24px;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}
.persona-card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }
.card-left { margin-right: 16px; }
.card-avatar, .card-avatar-placeholder {
  width: 56px; height: 56px; border-radius: 10px;
  background-size: cover; background-position: center;
}
.card-avatar-placeholder {
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 600;
}
.card-body { flex: 1; min-width: 0; }
.card-name-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.card-name { margin: 0; font-size: 16px; }
.card-text {
  margin: 0 0 4px; font-size: 14px; color: var(--color-text-secondary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 400px;
}
.card-tags { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px; }
.card-actions {
  display: flex; flex-direction: column; justify-content: center; gap: 4px; margin-left: 16px;
}
.empty-state { padding: 60px 0; }
.limit-hint { text-align: center; color: #e67e22; font-size: 13px; margin-top: 8px; }

.hint { color: #999; font-size: 12px; margin-top: 8px; }
.parse-preview { max-height: 60vh; overflow-y: auto; }
.preview-header { display: flex; align-items: center; gap: 16px; }
.preview-avatar { width: 64px; height: 64px; border-radius: 10px; background-size: cover; background-position: center; flex-shrink: 0; }
.preview-meta { color: #999; font-size: 13px; margin: 4px 0 0; }
.dup-warn { color: #e67e22; font-size: 13px; margin: 4px 0 0; }
.mvu-banner { margin: 12px 0; }
.mvu-banner-list { margin: 8px 0; padding-left: 24px; line-height: 1.7; font-size: 13px; }
.mvu-banner-list code { background: rgba(0,0,0,0.06); padding: 1px 4px; border-radius: 3px; font-size: 12px; }
.mvu-banner-note { margin: 6px 0 0; font-size: 12px; color: var(--color-text-tertiary); }
.parse-error { margin-top: 12px; }
</style>
