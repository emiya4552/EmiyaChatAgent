<template>
  <div class="sidebar">
    <div class="sidebar-header">
      <h2 class="logo">EMIYA</h2>
      <n-button size="small" type="primary" @click="openCreateDialog">
        + 新建对话
      </n-button>
    </div>

    <div class="conversation-list">
      <div
        v-for="conv in convStore.list"
        :key="conv.id"
        :class="['conv-item', { active: conv.id === convStore.currentId }]"
        @click="convStore.setCurrent(conv.id)"
      >
        <img
          v-if="personaAvatarUrl(conv)"
          class="conv-avatar"
          :src="personaAvatarUrl(conv)!"
          :alt="conv.persona_name || 'AI'"
        />
        <div v-else class="conv-avatar" :style="{ background: avatarColor(conv.persona_name || 'AI') }">
          {{ (conv.persona_name || 'AI')[0] }}
        </div>
        <div class="conv-info">
          <div class="conv-title">{{ conv.title || '新对话' }}</div>
          <div class="conv-meta">
            <span>{{ conv.persona_name || '未设人设' }}</span>
            <span>·</span>
            <span>{{ relativeTime(conv.updated_at) }}</span>
          </div>
        </div>
        <n-dropdown trigger="click" :options="convMenuOptions(conv)" @select="(key: string) => handleConvMenu(key, conv)">
          <span class="conv-menu-btn" @click.stop>···</span>
        </n-dropdown>
      </div>

      <div v-if="convStore.list.length === 0 && !convStore.loading" class="empty">
        暂无对话，点击上方按钮开始
      </div>
    </div>

    <div class="sidebar-nav">
      <router-link to="/personas" class="nav-item">
        <n-icon><PeopleOutline /></n-icon>
        <span>人设</span>
      </router-link>
      <router-link to="/memories" class="nav-item">
        <n-icon><BookOutline /></n-icon>
        <span>记忆</span>
      </router-link>
      <router-link to="/mood" class="nav-item">
        <n-icon><StatsChartOutline /></n-icon>
        <span>情绪</span>
      </router-link>
      <router-link to="/presets" class="nav-item">
        <n-icon><OptionsOutline /></n-icon>
        <span>预设</span>
      </router-link>
      <router-link to="/regex-presets" class="nav-item">
        <n-icon><CodeSlash /></n-icon>
        <span>正则</span>
      </router-link>
      <router-link to="/templates" class="nav-item">
        <n-icon><LayersOutline /></n-icon>
        <span>模板</span>
      </router-link>
      <router-link to="/worldbooks" class="nav-item">
        <n-icon><EarthOutline /></n-icon>
        <span>世界书</span>
      </router-link>
    </div>

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

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NDropdown, NIcon, NInput, NModal, NSelect, useMessage } from 'naive-ui'
import { BookOutline, PeopleOutline, StatsChartOutline, OptionsOutline, CodeSlash, LayersOutline, EarthOutline } from '@vicons/ionicons5'
import { useConversationStore } from '../../stores/conversation'
import { useChatStore } from '../../stores/chat'
import { fetchPersonas, fetchPersonaDetail } from '../../api/persona'
import { fetchPresets } from '../../api/preset'
import { fetchTemplates } from '../../api/template'
import { fetchWorldbooks } from '../../api/worldbook'
import { fetchRegexPresets } from '../../api/regexPreset'
import { avatarColor } from '../../utils/avatar'
import type { PersonaListItem, PresetInfo, TemplateListItem, WorldbookListItem, RegexPresetInfo } from '../../types'

const router = useRouter()
const convStore = useConversationStore()
const chatStore = useChatStore()
const message = useMessage()

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

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins}分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}天前`
  return new Date(dateStr).toLocaleDateString()
}

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
  // 懒加载 worldbook + regex 列表（避免侧栏每次挂载都拉）
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

function personaAvatarUrl(conv: { persona_id: string | null }): string | null {
  if (!conv.persona_id) return null
  const p = personas.value.find(p => p.id === conv.persona_id)
  return p?.avatar_url || null
}

// 三点菜单只保留"删除对话"——其它配置统一在右上齿轮里改（详见 ADR-0014）
function convMenuOptions(conv: { id: string }) {
  return [
    { label: '删除对话', key: `delete:${conv.id}` },
  ]
}

async function handleConvMenu(key: string, conv: { id: string }) {
  if (key === `delete:${conv.id}`) {
    try {
      await convStore.deleteById(conv.id)
      message.success('对话已删除')
    } catch {
      message.error('删除失败')
    }
  }
}

</script>

<style scoped>
.sidebar {
  width: 280px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-sidebar-bg);
  color: var(--color-sidebar-text);
}
.sidebar-header {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.logo {
  font-size: 20px;
  margin: 0;
  color: var(--color-primary);
}
.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.conv-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  margin-bottom: 2px;
  transition: background var(--transition-fast);
}
.conv-item:hover {
  background: var(--color-sidebar-hover);
}
.conv-item.active {
  background: var(--color-sidebar-active);
}
.conv-menu-btn {
  flex-shrink: 0;
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 4px;
  cursor: pointer;
  color: var(--color-sidebar-text-dim);
  font-size: 16px; font-weight: 700;
  transition: all var(--transition-fast);
}
.conv-menu-btn:hover {
  color: var(--color-sidebar-text);
  background: var(--color-sidebar-hover);
}
.conv-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  flex-shrink: 0;
  background-size: cover;
  background-position: center;
}
.conv-info {
  flex: 1;
  min-width: 0;
}
.conv-title {
  font-size: 14px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conv-meta {
  display: flex;
  gap: 4px;
  font-size: 12px;
  color: var(--color-sidebar-text-dim);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty {
  text-align: center;
  color: var(--color-sidebar-text-dim);
  padding: 24px;
  font-size: 14px;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  color: var(--color-sidebar-text-dim);
  text-decoration: none;
  font-size: 14px;
  transition: all var(--transition-fast);
}
.nav-item:hover {
  color: var(--color-sidebar-text);
  background: var(--color-sidebar-hover);
}
.nav-item.router-link-active {
  color: var(--color-primary);
  background: var(--color-sidebar-active);
}

.dialog-card {
  width: 480px;
  max-height: 86vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 12px;
  padding: 24px;
}
.dialog-title { margin: 0 0 20px; font-size: 18px; }
.dialog-field { margin-bottom: 16px; }
.dialog-field label { display: block; margin-bottom: 6px; font-size: 14px; color: #333; }
.label-hint { font-size: 12px; color: #999; font-weight: normal; }
.dialog-links { display: flex; justify-content: center; gap: 24px; margin-bottom: 20px; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 12px; padding-top: 16px; border-top: 1px solid #eee; }
</style>
