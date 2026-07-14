<template>
  <PageShell>
    <div class="page-header">
      <n-button text @click="$router.push('/worldbooks')">
        <template #icon><n-icon><ArrowBack /></n-icon></template>
        返回列表
      </n-button>
      <h2 class="page-title">
        <n-input v-model:value="book.name" placeholder="世界书名称" />
      </h2>
      <n-button @click="metaDialog = true">本书设置</n-button>
      <n-button type="primary" :loading="saving" @click="handleSave">保存</n-button>
    </div>

    <n-spin :show="loading">
      <div v-if="!loading" class="editor-layout">
        <!-- 左：条目列表 -->
        <div class="entry-list">
          <div class="list-actions">
            <n-button block type="primary" @click="addEntry">+ 新增条目</n-button>
          </div>
          <div class="entries">
            <div
              v-for="(e, idx) in book.entries"
              :key="e.uid"
              class="entry-row"
              :class="{ active: selectedIdx === idx, disabled: !e.enabled }"
              @click="selectedIdx = idx"
            >
              <n-switch
                size="small"
                :value="e.enabled"
                @click.stop
                @update:value="toggleEnabled(idx, $event)"
              />
              <div class="entry-name">
                {{ e.comment || `条目 #${e.uid}` }}
                <span v-if="e.constant" class="badge const">常驻</span>
                <span v-else-if="e.key.length" class="badge">{{ e.key.length }} key</span>
              </div>
              <n-button text size="small" type="error" @click.stop="removeEntry(idx)">×</n-button>
            </div>
          </div>
        </div>

        <!-- 右：条目编辑 -->
        <div class="entry-pane">
          <WorldbookEntryEditor
            :entry="selectedEntry"
            :book-defaults="bookDefaults"
            :detecting-output-contract="detectingOutputContract"
            :declaring-output-contract="declaringOutputContract"
            :confirming-output-contract="confirmingOutputContract"
            :updating-output-contract="updatingOutputContract"
            :restoring-output-contract="restoringOutputContract"
            :canonical-sections="canonicalSections"
            @detect-output-contract="detectSelectedEntryOutputContract"
            @declare-output-contract="declareSelectedEntryOutputContract"
            @save-output-contract-definition="saveSelectedEntryOutputContractDefinition"
            @confirm-output-contract="confirmSelectedEntryOutputContract"
            @update-output-contract="updateSelectedEntryOutputContract"
            @restore-auto-output-contract="restoreSelectedEntryOutputContractAuto"
          />
        </div>
      </div>
    </n-spin>

    <!-- 本书元数据 modal -->
    <n-modal v-model:show="metaDialog" preset="dialog" title="本书设置">
      <n-form-item label="描述" label-placement="top">
        <n-input v-model:value="book.description" type="textarea" :autosize="{ minRows: 2 }" />
      </n-form-item>
      <n-form-item label="扫描深度（默认）" label-placement="left">
        <n-input-number v-model:value="book.scan_depth" :min="0" :max="100" />
      </n-form-item>
      <n-form-item label="大小写敏感（默认）" label-placement="left">
        <n-switch v-model:value="book.case_sensitive" />
      </n-form-item>
      <n-form-item label="整词匹配（默认）" label-placement="left">
        <n-switch v-model:value="book.match_whole_words" />
      </n-form-item>
    </n-modal>
  </PageShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NIcon, NSpin, NInput, NSwitch, NInputNumber, NModal, NFormItem,
  useMessage,
} from 'naive-ui'
import { ArrowBack } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import WorldbookEntryEditor from '../components/worldbook/WorldbookEntryEditor.vue'
import {
  confirmWorldbookEntryOutputContract,
  declareWorldbookEntryOutputContract,
  detectWorldbookEntryOutputContract,
  fetchCanonicalSections,
  fetchWorldbook,
  updateWorldbook,
  updateWorldbookEntryOutputContract,
  restoreWorldbookEntryOutputContractAuto,
  type CanonicalSection,
} from '../api/worldbook'
import type { Worldbook, WorldbookEntry } from '../types'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const id = route.params.id as string

const loading = ref(true)
const saving = ref(false)
const detectingOutputContract = ref(false)
const declaringOutputContract = ref(false)
const confirmingOutputContract = ref(false)
const updatingOutputContract = ref(false)
const restoringOutputContract = ref(false)
const canonicalSections = ref<CanonicalSection[]>([])
const metaDialog = ref(false)
const selectedIdx = ref<number>(-1)
const book = ref<Worldbook>({
  id: '',
  user_id: null,
  name: '',
  description: null,
  scan_depth: 2,
  case_sensitive: false,
  match_whole_words: false,
  entries: [],
  extensions: {},
  created_at: '',
  updated_at: '',
})

const selectedEntry = computed<WorldbookEntry | null>(() => {
  if (selectedIdx.value < 0 || selectedIdx.value >= book.value.entries.length) return null
  return book.value.entries[selectedIdx.value]
})

// 把书级默认拍平给子组件做"继承"回退
const bookDefaults = computed(() => ({
  scan_depth: book.value.scan_depth,
  case_sensitive: book.value.case_sensitive,
  match_whole_words: book.value.match_whole_words,
}))

onMounted(async () => {
  try {
    book.value = await fetchWorldbook(id)
    if (book.value.entries.length > 0) selectedIdx.value = 0
  } catch (err: any) {
    message.error(err.response?.data?.detail || '加载失败')
    router.push('/worldbooks')
  } finally {
    loading.value = false
  }
  // canonical section 列表用于“显式声明输出模板”；失败不阻断编辑（声明区隐藏）。
  try {
    canonicalSections.value = await fetchCanonicalSections()
  } catch {
    canonicalSections.value = []
  }
})

function nextUid(): number {
  if (!book.value.entries.length) return 0
  return Math.max(...book.value.entries.map(e => e.uid)) + 1
}

function addEntry() {
  const newEntry: WorldbookEntry = {
    uid: nextUid(),
    comment: '新条目',
    enabled: true,
    content: '',
    constant: false,
    key: [],
    keysecondary: [],
    selective_logic: 0,
    scan_depth: null,
    case_sensitive: null,
    match_whole_words: null,
    position: 0,
    depth: 4,
    order: 100,
    role: 'system',
    ignore_budget: false,
    outlet_name: null,
    output_contract: null,
    extras: {},
  }
  book.value.entries.push(newEntry)
  selectedIdx.value = book.value.entries.length - 1
}

function removeEntry(idx: number) {
  book.value.entries.splice(idx, 1)
  if (selectedIdx.value >= book.value.entries.length) {
    selectedIdx.value = book.value.entries.length - 1
  }
}

function toggleEnabled(idx: number, v: boolean) {
  book.value.entries[idx].enabled = v
}

async function handleSave() {
  saving.value = true
  try {
    const updated = await updateWorldbook(id, {
      name: book.value.name,
      description: book.value.description,
      scan_depth: book.value.scan_depth,
      case_sensitive: book.value.case_sensitive,
      match_whole_words: book.value.match_whole_words,
      entries: book.value.entries,
    })
    book.value = updated
    message.success('已保存')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function saveBookSilently(): Promise<void> {
  const updated = await updateWorldbook(id, {
    name: book.value.name,
    description: book.value.description,
    scan_depth: book.value.scan_depth,
    case_sensitive: book.value.case_sensitive,
    match_whole_words: book.value.match_whole_words,
    entries: book.value.entries,
  })
  book.value = updated
}

async function detectSelectedEntryOutputContract() {
  const entry = selectedEntry.value
  if (!entry) return
  detectingOutputContract.value = true
  try {
    await saveBookSilently()
    const updated = await detectWorldbookEntryOutputContract(id, entry.uid)
    book.value = updated
    const idx = book.value.entries.findIndex(e => e.uid === entry.uid)
    if (idx >= 0) selectedIdx.value = idx
    message.success('AI 输出格式识别已完成')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '识别失败')
  } finally {
    detectingOutputContract.value = false
  }
}

async function declareSelectedEntryOutputContract(
  payload: { mode: string; section_names: string[] },
) {
  const entry = selectedEntry.value
  if (!entry) return
  declaringOutputContract.value = true
  try {
    await saveBookSilently()
    const updated = await declareWorldbookEntryOutputContract(id, entry.uid, payload)
    book.value = updated
    const idx = book.value.entries.findIndex(e => e.uid === entry.uid)
    if (idx >= 0) selectedIdx.value = idx
    message.success('输出模板已声明（source=manual，最高权威）')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '声明失败')
  } finally {
    declaringOutputContract.value = false
  }
}

async function saveSelectedEntryOutputContractDefinition(
  payload: { definition: Record<string, unknown> },
) {
  const entry = selectedEntry.value
  if (!entry) return
  declaringOutputContract.value = true
  try {
    await saveBookSilently()
    const updated = await updateWorldbookEntryOutputContract(id, entry.uid, payload)
    book.value = updated
    const idx = book.value.entries.findIndex(e => e.uid === entry.uid)
    if (idx >= 0) selectedIdx.value = idx
    message.success('输出契约定义已保存')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存契约定义失败')
  } finally {
    declaringOutputContract.value = false
  }
}

async function confirmSelectedEntryOutputContract() {
  const entry = selectedEntry.value
  if (!entry) return
  confirmingOutputContract.value = true
  try {
    await saveBookSilently()
    const updated = await confirmWorldbookEntryOutputContract(id, entry.uid)
    book.value = updated
    const idx = book.value.entries.findIndex(e => e.uid === entry.uid)
    if (idx >= 0) selectedIdx.value = idx
    message.success('已确认识别结果（reviewed=true）')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '确认失败')
  } finally {
    confirmingOutputContract.value = false
  }
}

async function updateSelectedEntryOutputContract(payload: { enabled: boolean }) {
  const entry = selectedEntry.value
  if (!entry) return
  updatingOutputContract.value = true
  try {
    await saveBookSilently()
    const updated = await updateWorldbookEntryOutputContract(id, entry.uid, payload)
    book.value = updated
    const idx = book.value.entries.findIndex(e => e.uid === entry.uid)
    if (idx >= 0) selectedIdx.value = idx
    message.success(payload.enabled ? '输出契约已启用' : '输出契约已禁用')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '更新契约失败')
  } finally {
    updatingOutputContract.value = false
  }
}

async function restoreSelectedEntryOutputContractAuto() {
  const entry = selectedEntry.value
  if (!entry) return
  restoringOutputContract.value = true
  try {
    await saveBookSilently()
    const updated = await restoreWorldbookEntryOutputContractAuto(id, entry.uid)
    book.value = updated
    const idx = book.value.entries.findIndex(e => e.uid === entry.uid)
    if (idx >= 0) selectedIdx.value = idx
    message.success('已恢复自动识别候选')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '恢复自动候选失败')
  } finally {
    restoringOutputContract.value = false
  }
}
</script>

<style scoped>
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.page-title { flex: 1; margin: 0; }
.editor-layout {
  display: grid; grid-template-columns: 320px 1fr;
  gap: 16px; height: calc(100vh - 200px); min-height: 500px;
}
.entry-list {
  background: var(--color-bg-surface); border-radius: var(--radius-md);
  display: flex; flex-direction: column;
}
.list-actions { padding: 12px; border-bottom: 1px solid var(--color-border); }
.entries { flex: 1; overflow-y: auto; }
.entry-row {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
}
.entry-row:hover { background: var(--color-bg-hover); }
.entry-row.active { background: var(--color-primary-bg); }
.entry-row.disabled .entry-name { color: var(--color-text-tertiary); text-decoration: line-through; }
.entry-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
.badge {
  margin-left: 6px; font-size: 11px; padding: 1px 6px; border-radius: 4px;
  background: var(--color-bg-hover); color: var(--color-text-secondary);
}
.badge.const { background: #fff2d6; color: #b06a00; }
.entry-pane {
  background: var(--color-bg-surface); border-radius: var(--radius-md);
  overflow-y: auto;
}
</style>
