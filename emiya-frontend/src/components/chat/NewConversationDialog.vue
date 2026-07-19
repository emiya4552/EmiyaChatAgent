<!--
  无界面的"新建对话"弹窗宿主。原 ChatSidebar 拆分而来:会话列表已上移到顶部对话
  副导航(AppNav),这里只保留创建弹窗 + 其联动逻辑(persona→世界书/正则预填、预设赢
  等,ADR-0014)。由顶部「＋ 新建对话」经 chatUi.newConvSignal 触发。
-->
<template>
  <n-modal :show="showDialog" @update:show="showDialog = $event">
    <div class="dialog-card">
      <h3 class="dialog-title">新建对话</h3>

      <div class="dialog-field">
        <label>AI 角色</label>
        <n-select v-model:value="selectedPersonaId" :options="aiPersonaOptions" placeholder="选择 AI 人设" @update:value="onPersonaPicked" />
      </div>

      <div class="dialog-field">
        <label>我的角色</label>
        <n-select v-model:value="selectedUserPersonaId" :options="userPersonaOptions" placeholder="选择你的角色（可选）" clearable />
      </div>

      <div class="dialog-field">
        <label>对话标题 <span class="label-hint">（可选，留空自动生成）</span></label>
        <n-input v-model:value="titleInput" placeholder="给这段对话取个名字..." maxlength="100" />
      </div>

      <div class="dialog-field">
        <label>预设 <span class="label-hint">（可选）</span></label>
        <n-select v-model:value="selectedPreset" :options="presetOptions" @update:value="onPresetPicked" />
      </div>

      <div class="dialog-field">
        <label>Prompt 模板 <span class="label-hint">（可选，留空用系统默认）</span></label>
        <n-select v-model:value="selectedTemplate" :options="templateOptions" />
      </div>

      <div class="dialog-field">
        <label>世界书 <span class="label-hint">（多选，顺序敏感；选了人设会自动填充其默认世界书）</span></label>
        <n-select
          v-model:value="selectedWorldbooks"
          multiple
          :options="worldbookOptions"
          placeholder="选择激活的世界书"
          :loading="loadingWorldbooks"
        />
      </div>

      <div class="dialog-field">
        <label>正则预设 <span class="label-hint">（可选，预设/人设带的正则会自动填）</span></label>
        <n-select
          v-model:value="selectedRegexPreset"
          :options="regexPresetOptions"
          :loading="loadingRegexPresets"
          clearable
        />
      </div>

      <div class="dialog-links">
        <n-button text type="primary" @click="goManagePersonas">
          管理人设 →
        </n-button>
      </div>

      <div class="dialog-actions">
        <n-button @click="showDialog = false">取消</n-button>
        <n-button type="primary" :disabled="!selectedPersonaId" @click="handleCreate">
          开始对话
        </n-button>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NInput, NModal, NSelect, useMessage } from 'naive-ui'
import { useConversationStore } from '../../stores/conversation'
import { useChatStore } from '../../stores/chat'
import { useChatUiStore } from '../../stores/chatUi'
import { fetchPersonas, fetchPersonaDetail } from '../../api/persona'
import { fetchPresets } from '../../api/preset'
import { fetchTemplates } from '../../api/template'
import { fetchWorldbooks } from '../../api/worldbook'
import { fetchRegexPresets } from '../../api/regexPreset'
import type { PersonaListItem, PresetInfo, TemplateListItem, WorldbookListItem, RegexPresetInfo } from '../../types'

const router = useRouter()
const convStore = useConversationStore()
const chatStore = useChatStore()
const chatUi = useChatUiStore()
const message = useMessage()

// 顶部「＋ 新建对话」副导航项 → 打开创建弹窗。
watch(() => chatUi.newConvSignal, () => { openCreateDialog() })

const NONE_PRESET = '__none__'
const NONE_TEMPLATE = '__none__'

const showDialog = ref(false)
const selectedPersonaId = ref<string | null>(null)
const selectedUserPersonaId = ref<string | null>(null)
const selectedPreset = ref<string>(NONE_PRESET)
const selectedTemplate = ref<string>(NONE_TEMPLATE)
const selectedWorldbooks = ref<string[]>([])
const selectedRegexPreset = ref<string | null>(null)
const titleInput = ref('')

const personas = ref<PersonaListItem[]>([])
const presets = ref<PresetInfo[]>([])
const templates = ref<TemplateListItem[]>([])
const worldbooks = ref<WorldbookListItem[]>([])
const regexPresets = ref<RegexPresetInfo[]>([])
const loadingWorldbooks = ref(false)
const loadingRegexPresets = ref(false)

const presetOptions = computed(() => [
  { label: '默认（无预设）', value: NONE_PRESET },
  ...presets.value
    .filter(p => p.name !== '默认')
    .map(p => ({ label: `${p.name} (${p.prompt_count}个Prompt)`, value: p.id })),
])

const templateOptions = computed(() => [
  { label: '系统默认（内置）', value: NONE_TEMPLATE },
  ...templates.value.map(t => ({
    label: t.is_default ? `${t.name}（首选）` : t.name,
    value: t.id,
  })),
])

const worldbookOptions = computed(() =>
  worldbooks.value.map(w => ({
    label: `${w.name}${w.is_template ? ' (模板)' : ''}`,
    value: w.id,
  }))
)

const regexPresetOptions = computed(() =>
  regexPresets.value.map(rp => ({
    label: `${rp.name} (${rp.script_count}条)`,
    value: rp.id,
  }))
)

const aiPersonaOptions = computed(() =>
  personas.value.map(p => ({ label: p.name, value: p.id }))
)
const userPersonaOptions = computed(() => [
  { label: '默认（不指定）', value: null as any },
  ...personas.value.map(p => ({ label: p.name, value: p.id })),
])

onMounted(async () => {
  try {
    const [pList, prList, tList] = await Promise.all([
      fetchPersonas('all'),
      fetchPresets(),
      fetchTemplates(),
    ])
    personas.value = pList
    presets.value = prList
    templates.value = tList
    const aiFirst = pList.find(p => !p.is_template)
    if (aiFirst) {
      selectedPersonaId.value = aiFirst.id
    }
    // 用户的首选模板（is_default=true）作为创建弹窗的默认选中项；
    // 未设首选时回退到"系统默认（内置）"。
    const preferred = tList.find(t => t.is_default)
    if (preferred) {
      selectedTemplate.value = preferred.id
    }
  } catch {
    // non-blocking
  }
})

async function openCreateDialog() {
  showDialog.value = true
  const aiFirst = personas.value.find(p => !p.is_template)
  if (aiFirst && !selectedPersonaId.value) {
    selectedPersonaId.value = aiFirst.id
  }
  // 懒加载 worldbook + regex 列表（避免每次挂载都拉）
  if (!worldbooks.value.length && !loadingWorldbooks.value) {
    loadingWorldbooks.value = true
    try {
      worldbooks.value = await fetchWorldbooks()
    } catch {
      // 静默；用户依然能创建对话，只是世界书 select 显示为空
    } finally {
      loadingWorldbooks.value = false
    }
  }
  if (!regexPresets.value.length && !loadingRegexPresets.value) {
    loadingRegexPresets.value = true
    try {
      regexPresets.value = await fetchRegexPresets()
    } catch {
      // 静默
    } finally {
      loadingRegexPresets.value = false
    }
  }
  // 选中默认 persona 后自动填默认 worldbook / regex（onPersonaPicked 做完整逻辑）
  if (selectedPersonaId.value) {
    await onPersonaPicked(selectedPersonaId.value)
  }
}

/**
 * 选 persona 时联动填充世界书 + 正则（关联预导入 step 1）。
 * 详见 ADR-0014：用户后续选预设会再次覆盖正则（"预设赢"）。
 */
async function onPersonaPicked(personaId: string | null) {
  if (!personaId) {
    selectedWorldbooks.value = []
    selectedRegexPreset.value = null
    return
  }
  try {
    const detail = await fetchPersonaDetail(personaId)
    selectedWorldbooks.value = [...(detail.default_worldbook_ids || [])]
    selectedRegexPreset.value = detail.default_regex_preset_id || null
  } catch {
    selectedWorldbooks.value = []
    selectedRegexPreset.value = null
  }
}

/**
 * 选 preset 时联动切换正则（关联预导入 step 2）。
 * preset.regex_preset_id 覆盖 persona 给的——"预设赢"是 ADR-0014 已确认决策。
 * preset 没有关联正则时，保留 persona 已填的，不清空。
 */
function onPresetPicked(presetId: string) {
  if (presetId === NONE_PRESET) return
  const preset = presets.value.find(p => p.id === presetId)
  if (preset && preset.regex_preset_id) {
    selectedRegexPreset.value = preset.regex_preset_id
  }
}

function goManagePersonas() {
  showDialog.value = false
  router.push('/personas')
}

// ADR-0017：开场白不再在创建前选——创建直接走 first_message，
// 进入对话后由 ChatMain/MessageBubble 上的左右切换按钮决定最终用哪一个。
async function handleCreate() {
  if (!selectedPersonaId.value) return
  showDialog.value = false

  const options: import('../../api/conversation').CreateConversationOptions = {
    title: titleInput.value.trim() || undefined,
    userPersonaId: selectedUserPersonaId.value || undefined,
    presetId: selectedPreset.value === NONE_PRESET ? undefined : selectedPreset.value,
    templateId: selectedTemplate.value === NONE_TEMPLATE ? undefined : selectedTemplate.value,
    regexPresetId: selectedRegexPreset.value || undefined,
    worldbookIds: selectedWorldbooks.value,
    // greetingIndex 不传 = 后端默认 first_message
  }
  const personaId = selectedPersonaId.value

  // 重置弹窗状态
  titleInput.value = ''
  selectedPreset.value = NONE_PRESET
  const preferred = templates.value.find(t => t.is_default)
  selectedTemplate.value = preferred ? preferred.id : NONE_TEMPLATE
  selectedRegexPreset.value = null

  try {
    chatStore.clearMessages()
    await convStore.create(personaId, options)
  } catch {
    message.error('创建对话失败')
  }
}
</script>

<style scoped>
.dialog-card {
  width: 480px;
  max-height: 86vh;
  overflow-y: auto;
  background: var(--color-bg-surface);
  border-radius: 12px;
  padding: 24px;
}
.dialog-title { margin: 0 0 20px; font-size: 18px; }
.dialog-field { margin-bottom: 16px; }
.dialog-field label { display: block; margin-bottom: 6px; font-size: 14px; color: var(--color-text); }
.label-hint { font-size: 12px; color: var(--color-text-tertiary); font-weight: normal; }
.dialog-links { display: flex; justify-content: center; gap: 24px; margin-bottom: 20px; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 12px; padding-top: 16px; border-top: 1px solid var(--color-border-light); }
</style>
