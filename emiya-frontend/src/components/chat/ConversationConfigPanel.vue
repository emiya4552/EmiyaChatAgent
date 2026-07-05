<template>
  <div class="config-panel">
    <h3 class="config-title">对话设置</h3>

    <n-collapse default-expanded-names="bindings">
      <n-collapse-item title="预设 / 模板 / 正则 / 世界书" name="bindings">
        <div class="bindings-grid">
          <n-form-item label="预设" label-placement="left">
            <n-select
              v-model:value="bindingsLocal.preset_id"
              :options="presetOptions"
              :loading="loadingBindings"
              clearable
              placeholder="无预设"
              style="width: 100%"
            />
          </n-form-item>
          <n-form-item label="Prompt 模板" label-placement="left">
            <n-select
              v-model:value="bindingsLocal.template_id"
              :options="templateOptions"
              :loading="loadingBindings"
              clearable
              placeholder="系统默认（内置）"
              style="width: 100%"
            />
          </n-form-item>
          <n-form-item label="正则预设" label-placement="left">
            <n-select
              v-model:value="bindingsLocal.regex_preset_id"
              :options="regexPresetOptions"
              :loading="loadingBindings"
              clearable
              placeholder="无正则"
              style="width: 100%"
            />
          </n-form-item>
          <n-form-item label="世界书绑定" label-placement="top">
            <n-select
              v-model:value="boundIds"
              multiple
              :options="wbOptions"
              placeholder="选择激活的世界书（顺序敏感）"
              :loading="loadingWb"
            />
          </n-form-item>
          <p class="hint">
            预设、模板、正则、世界书都是对话级独立绑定；切预设不会自动改正则，
            如需联动请重建对话。
          </p>
        </div>
      </n-collapse-item>

      <n-collapse-item title="采样参数" name="sampling">
        <div class="params-grid">
          <n-form-item label="Temperature" label-placement="left">
            <n-input-number v-model:value="localConfig.temperature" :min="0" :max="2" :step="0.05" />
          </n-form-item>
          <n-form-item label="Top P" label-placement="left">
            <n-input-number v-model:value="localConfig.top_p" :min="0" :max="1" :step="0.01" />
          </n-form-item>
          <n-form-item label="Top K" label-placement="left">
            <n-input-number v-model:value="localConfig.top_k" :min="0" :max="200" :step="1" />
          </n-form-item>
          <n-form-item label="Min P" label-placement="left">
            <n-input-number v-model:value="localConfig.min_p" :min="0" :max="1" :step="0.01" />
          </n-form-item>
          <n-form-item label="Frequency Penalty" label-placement="left">
            <n-input-number v-model:value="localConfig.frequency_penalty" :min="-2" :max="2" :step="0.01" />
          </n-form-item>
          <n-form-item label="Presence Penalty" label-placement="left">
            <n-input-number v-model:value="localConfig.presence_penalty" :min="-2" :max="2" :step="0.01" />
          </n-form-item>
          <n-form-item label="Repetition Penalty" label-placement="left">
            <n-input-number v-model:value="localConfig.repetition_penalty" :min="1" :max="2" :step="0.01" />
          </n-form-item>
        </div>
      </n-collapse-item>

      <n-collapse-item title="上下文设置" name="context">
        <div class="params-grid">
          <n-form-item label="上下文窗口 Token" label-placement="left">
            <n-input-number v-model:value="localConfig.openai_max_context" :min="1000" :max="2000000" :step="1000" />
          </n-form-item>
          <p class="hint">
            单次请求发给 LLM 的 token 总预算（system prompt + 对话历史 + 输出预留），
            对应模型本身的上下文窗口容量。注：对话历史的滑动窗口由后端按消息条数控制
            （`WINDOW_SIZE`），溢出消息会被压缩为摘要，与该值无关。
          </p>
          <n-form-item label="最大输出 Token" label-placement="left">
            <n-input-number v-model:value="localConfig.openai_max_tokens" :min="256" :max="131072" :step="256" />
          </n-form-item>
          <p class="hint">
            LLM 单次回复的 token 上限，超出由 LLM 端强制截断。
          </p>
          <n-form-item label="世界书预算 %" label-placement="left">
            <n-input-number v-model:value="localConfig.worldbook_budget_pct" :min="0" :max="100" :step="1" />
          </n-form-item>
        </div>
      </n-collapse-item>

      <n-collapse-item :title="`对话状态变量 (${variablesCount})`" name="variables">
        <p class="hint">
          这些变量由角色卡 / 世界书 / 预设里的
          <code v-pre>{{setvar}}</code> / <code v-pre>{{incvar}}</code>
          等宏在每轮对话中读写；只对当前对话有效。如发现变量被脚本写坏，可整体重置。
        </p>
        <div v-if="mvuState?.initialized || mvuState?.source_count" class="mvu-state">
          <div class="mvu-state-row">
            <span>初始化源 {{ mvuState.source_count }}</span>
            <span>字段 {{ mvuState.field_count }}</span>
            <span v-if="mvuState.last_reload_at">最近重载 {{ formatDateTime(mvuState.last_reload_at) }}</span>
          </div>
          <p v-if="mvuState.warnings?.length" class="mvu-warning">
            {{ mvuState.warnings[0] }}
          </p>
        </div>
        <div v-if="mvuRuntimeView?.is_mvu" class="mvu-runtime">
          <div class="mvu-runtime-head">
            MVU 运行时诊断（上一轮）
            <span class="mvu-runtime-counts">
              <span v-for="(n, role) in mvuRuntimeView.counts" :key="role">{{ role }}×{{ n }}</span>
            </span>
          </div>
          <ul class="mvu-runtime-list">
            <li v-for="(e, i) in mvuRuntimeView.entries" :key="i" :title="e.role_label">
              <span class="mvu-role">{{ e.role }}</span>
              <span class="mvu-comment" :title="e.comment">{{ e.comment }}</span>
              <span class="mvu-chars">{{ e.chars }}字</span>
            </li>
          </ul>
          <div v-if="mvuRuntimeView.update" class="mvu-update">
            <div class="mvu-update-head">
              <span>变量更新</span>
              <span :class="['mvu-update-channel', `is-${mvuRuntimeView.update.channel}`]">
                {{ mvuRuntimeView.update.channel }}
              </span>
              <span>applied×{{ mvuRuntimeView.update.applied }}</span>
              <span v-if="mvuRuntimeView.update.meta">
                tool calls×{{ mvuRuntimeView.update.meta.tool_calls_received ?? 0 }}
              </span>
            </div>
            <div v-if="mvuRuntimeView.update.meta" class="mvu-update-meta">
              <span>enabled={{ formatBool(mvuRuntimeView.update.meta.enabled_flag) }}</span>
              <span>uses_mvu={{ formatBool(mvuRuntimeView.update.meta.persona_uses_mvu) }}</span>
              <span>tools_sent={{ formatBool(mvuRuntimeView.update.meta.tools_sent) }}</span>
              <span>tools×{{ mvuRuntimeView.update.meta.tool_count ?? 0 }}</span>
              <span>[mvu_update]×{{ mvuRuntimeView.update.meta.mvu_update_entries ?? 0 }}</span>
            </div>
            <details
              v-if="hasUpdateDetails(mvuRuntimeView.update)"
              class="mvu-update-details"
            >
              <summary>更新细节</summary>
              <div v-if="mvuRuntimeView.update.coerced.length">
                <strong>coerced</strong>
                <p v-for="(item, i) in mvuRuntimeView.update.coerced" :key="`coerced-${i}`">
                  {{ item.path }}: {{ formatDiagValue(item.from) }} → {{ formatDiagValue(item.to) }}
                </p>
              </div>
              <div v-if="mvuRuntimeView.update.clamped.length">
                <strong>clamped</strong>
                <p v-for="(item, i) in mvuRuntimeView.update.clamped" :key="`clamped-${i}`">
                  {{ item.path }} → {{ formatDiagValue(item.to) }}
                </p>
              </div>
              <div v-if="mvuRuntimeView.update.dropped.length">
                <strong>dropped</strong>
                <p v-for="(item, i) in mvuRuntimeView.update.dropped" :key="`dropped-${i}`">
                  {{ item.path || '(unknown)' }}: {{ item.reason }}
                </p>
              </div>
              <div v-if="mvuRuntimeView.update.meta?.tool_call_names?.length">
                <strong>tool calls</strong>
                <p>{{ mvuRuntimeView.update.meta.tool_call_names.join(', ') }}</p>
              </div>
            </details>
          </div>
          <p v-for="(d, i) in mvuRuntimeView.diagnostics" :key="'d' + i" class="mvu-diag">{{ d }}</p>
        </div>
        <div v-if="variablesEntries.length === 0" class="empty-vars">
          当前对话尚未设置任何变量
        </div>
        <div v-else class="vars-table">
          <div class="vars-row vars-head">
            <span class="vars-key">key</span>
            <span class="vars-val">value</span>
          </div>
          <div v-for="[k, v] in variablesEntries" :key="k" class="vars-row">
            <span class="vars-key" :title="k">{{ k }}</span>
            <span class="vars-val" :title="formatVarValue(v)">{{ formatVarValue(v) }}</span>
          </div>
        </div>
        <div class="vars-actions">
          <n-button
            v-if="showMvuActions"
            size="small"
            :loading="reloadingVars"
            @click="reloadInitialState"
          >
            补全缺失初始变量
          </n-button>
          <n-button
            v-if="variablesEntries.length > 0"
            size="small"
            type="error"
            ghost
            :loading="resettingVars"
            @click="resetVariables"
          >
            重置所有变量
          </n-button>
        </div>
      </n-collapse-item>

      <n-collapse-item title="功能开关" name="features">
        <div class="params-grid">
          <n-form-item label="情绪分析" label-placement="left">
            <n-switch v-model:value="togglesLocal.analyze_emotion" />
            <span class="switch-hint">关闭后跳过每轮情绪 LLM 调用（不写 EmotionRecord / 不更新 mood / SSE emotion 不发）；前端 mood emoji 和趋势图也不再更新</span>
          </n-form-item>
          <n-form-item label="卡界面危险能力" label-placement="left">
            <n-switch :value="mvuDangerousLocal" :loading="mvuCapSaving" @update:value="onToggleMvuDangerous" />
            <span class="switch-hint">ADR-0008d：允许卡界面（如手机终端）调用 LLM 生成（generateRaw，花 token）与修改会话楼层（setChatMessages）。默认关闭，仅对信任的卡开启。read/本地能力不受此限。</span>
          </n-form-item>
        </div>
      </n-collapse-item>

      <n-collapse-item title="Author's Note 作者笔记" name="an">
        <n-form-item label="内容" label-placement="top">
          <n-input
            v-model:value="anLocal.author_note"
            type="textarea"
            placeholder="一段对 AI 的飘浮指令，会插入到聊天历史末尾倒数第 N 条之前"
            :autosize="{ minRows: 3, maxRows: 8 }"
          />
        </n-form-item>
        <n-form-item label="深度 (倒数第 N 条)" label-placement="left">
          <n-input-number v-model:value="anLocal.an_depth" :min="0" :max="100" />
        </n-form-item>
        <n-form-item label="role" label-placement="left">
          <n-select
            v-model:value="anLocal.an_role"
            :options="AN_ROLE_OPTIONS"
            style="width: 200px"
          />
        </n-form-item>
        <n-form-item label="间隔 (每 N 轮插一次, 1=每次)" label-placement="left">
          <n-input-number v-model:value="anLocal.an_interval" :min="1" :max="100" />
        </n-form-item>
      </n-collapse-item>
    </n-collapse>

    <div class="config-actions">
      <n-button @click="$emit('close')">取消</n-button>
      <n-button type="primary" :loading="saving" @click="handleSave">保存</n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NButton, NCollapse, NCollapseItem, NFormItem, NInput, NInputNumber, NSelect,
  NSwitch, useMessage,
} from 'naive-ui'
import { useConversationStore } from '../../stores/conversation'
import { useChatStore } from '../../stores/chat'
import {
  updateConversationConfig, updateConversationToggles, clearConversationVariables,
  reloadMvuInitialState, setMvuCapabilities,
  applyPreset, switchTemplate, switchRegexPreset,
} from '../../api/conversation'
import {
  fetchWorldbooks, updateConversationWorldbooks, updateConversationAuthorNote,
} from '../../api/worldbook'
import { fetchPresets } from '../../api/preset'
import { fetchTemplates } from '../../api/template'
import { fetchRegexPresets } from '../../api/regexPreset'
import type {
  ChatConfig, WorldbookListItem, PresetInfo, TemplateListItem, RegexPresetInfo,
  MvuUpdateInfo,
} from '../../types'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ close: [] }>()

const convStore = useConversationStore()
const chatStore = useChatStore()
const message = useMessage()
// MVU 诊断运行时视图（ADR-0003 §3）：随最近一轮 message_done 派生
const mvuRuntimeView = computed(() => chatStore.mvuRuntimeView)
const saving = ref(false)

const currentConv = computed(() =>
  convStore.list.find(c => c.id === convStore.currentId) || null
)

const localConfig = ref<ChatConfig>({})
const boundIds = ref<string[]>([])
const wbList = ref<WorldbookListItem[]>([])
const loadingWb = ref(false)

// 预设 / 模板 / 正则三件套：合并到一个"绑定"折叠区
const bindingsLocal = ref<{
  preset_id: string | null
  template_id: string | null
  regex_preset_id: string | null
}>({ preset_id: null, template_id: null, regex_preset_id: null })
const bindingsInitial = ref<{
  preset_id: string | null
  template_id: string | null
  regex_preset_id: string | null
}>({ preset_id: null, template_id: null, regex_preset_id: null })
const presetList = ref<PresetInfo[]>([])
const templateList = ref<TemplateListItem[]>([])
const regexPresetList = ref<RegexPresetInfo[]>([])
const loadingBindings = ref(false)
const anLocal = ref<{
  author_note: string
  an_depth: number
  an_role: string
  an_interval: number
}>({
  author_note: '',
  an_depth: 4,
  an_role: 'system',
  an_interval: 1,
})
const togglesLocal = ref<{ analyze_emotion: boolean }>({ analyze_emotion: true })

// ── ADR-0008d：MVU 卡界面危险能力 per-conversation 开关（即时保存，独立于下方 saveAll）──
const mvuDangerousLocal = ref(false)
const mvuCapSaving = ref(false)
async function onToggleMvuDangerous(val: boolean) {
  const convId = convStore.currentId
  if (!convId) return
  mvuCapSaving.value = true
  try {
    const updated = await setMvuCapabilities(convId, val)
    const idx = convStore.list.findIndex(c => c.id === convId)
    if (idx !== -1) convStore.list[idx] = { ...convStore.list[idx], mvu_capabilities: updated.mvu_capabilities }
    mvuDangerousLocal.value = val
    message.success(val ? '已开启卡界面危险能力（下次载卡生效）' : '已关闭卡界面危险能力')
  } catch (e: any) {
    message.error('保存失败：' + (e?.message || e))
  } finally {
    mvuCapSaving.value = false
  }
}

// ── MVU 对话级变量展示 ──
const variablesEntries = computed<[string, unknown][]>(() => {
  const v = currentConv.value?.variables || {}
  // MVU 卡形态：variables = {stat_data: {...嵌套树}, initialized_lorebooks: {...}, schema: "..."}
  // 优先展开 stat_data 子键，这是用户关心的"状态栏字段"（详见 ADR-0010）
  if (v && typeof v === 'object' && 'stat_data' in (v as any)) {
    const sd = (v as any).stat_data
    if (sd && typeof sd === 'object' && !Array.isArray(sd)) {
      return Object.entries(sd)
    }
  }
  return Object.entries(v)
})
const variablesCount = computed(() => variablesEntries.value.length)
const resettingVars = ref(false)
const reloadingVars = ref(false)
const mvuState = computed(() => currentConv.value?.mvu_state || null)
const showMvuActions = computed(() => {
  const state = mvuState.value
  return Boolean(state?.initialized || state?.source_count || variablesCount.value > 0)
})

function formatVarValue(v: unknown): string {
  if (v === null) return 'null'
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

function formatDateTime(v: string): string {
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleString()
}

function formatBool(v: unknown): string {
  return v ? 'true' : 'false'
}

function formatDiagValue(v: unknown): string {
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

function hasUpdateDetails(update: MvuUpdateInfo): boolean {
  return Boolean(
    update.coerced.length ||
    update.clamped.length ||
    update.dropped.length ||
    update.meta?.tool_call_names?.length
  )
}

async function resetVariables() {
  const convId = convStore.currentId
  if (!convId) return
  resettingVars.value = true
  try {
    const updated = await clearConversationVariables(convId)
    const idx = convStore.list.findIndex(c => c.id === convId)
    if (idx !== -1) {
      convStore.list[idx] = {
        ...convStore.list[idx],
        variables: updated.variables,
        mvu_state: updated.mvu_state,
      }
    }
    message.success('对话状态变量已重置')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '重置失败')
  } finally {
    resettingVars.value = false
  }
}

async function reloadInitialState() {
  const convId = convStore.currentId
  if (!convId) return
  reloadingVars.value = true
  try {
    const updated = await reloadMvuInitialState(convId)
    const idx = convStore.list.findIndex(c => c.id === convId)
    if (idx !== -1) {
      convStore.list[idx] = { ...convStore.list[idx], ...updated }
    }
    message.success('已补全缺失的 MVU 初始变量')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '补全失败')
  } finally {
    reloadingVars.value = false
  }
}

const wbOptions = computed(() =>
  wbList.value.map(w => ({
    label: `${w.name}${w.is_template ? ' (模板)' : ''}`,
    value: w.id,
  }))
)

const presetOptions = computed(() =>
  presetList.value
    .filter(p => p.name !== '默认')
    .map(p => ({ label: `${p.name} (${p.prompt_count}个Prompt)`, value: p.id }))
)

const templateOptions = computed(() =>
  templateList.value.map(t => ({
    label: t.is_default ? `${t.name}（首选）` : t.name,
    value: t.id,
  }))
)

const regexPresetOptions = computed(() =>
  regexPresetList.value.map(rp => ({
    label: `${rp.name} (${rp.script_count}条)`,
    value: rp.id,
  }))
)

const AN_ROLE_OPTIONS = [
  { label: 'system', value: 'system' },
  { label: 'user', value: 'user' },
  { label: 'assistant', value: 'assistant' },
]

watch(() => props.visible, async (v) => {
  if (!v) return
  const conv = currentConv.value
  const source = conv?.effective_chat_config ?? conv?.chat_config ?? {}
  localConfig.value = { ...source }
  boundIds.value = [...(conv?.worldbook_ids ?? [])]
  anLocal.value = {
    author_note: conv?.author_note ?? '',
    an_depth: conv?.an_depth ?? 4,
    an_role: conv?.an_role ?? 'system',
    an_interval: conv?.an_interval ?? 1,
  }
  togglesLocal.value = {
    analyze_emotion: conv?.analyze_emotion ?? true,
  }
  mvuDangerousLocal.value = !!((conv?.mvu_capabilities as any)?.dangerous)
  // 三件套绑定快照 — 保存时与 initial 对比，只发起改过的字段
  const snap = {
    preset_id: conv?.preset_id ?? null,
    template_id: conv?.template_id ?? null,
    regex_preset_id: conv?.regex_preset_id ?? null,
  }
  bindingsLocal.value = { ...snap }
  bindingsInitial.value = { ...snap }
  // 懒加载世界书列表
  if (!wbList.value.length) {
    loadingWb.value = true
    try {
      wbList.value = await fetchWorldbooks()
    } catch {
      message.error('加载世界书列表失败')
    } finally {
      loadingWb.value = false
    }
  }
  // 懒加载预设 / 模板 / 正则
  if (!presetList.value.length || !templateList.value.length || !regexPresetList.value.length) {
    loadingBindings.value = true
    try {
      const [p, t, rp] = await Promise.all([
        presetList.value.length ? Promise.resolve(presetList.value) : fetchPresets(),
        templateList.value.length ? Promise.resolve(templateList.value) : fetchTemplates(),
        regexPresetList.value.length ? Promise.resolve(regexPresetList.value) : fetchRegexPresets(),
      ])
      presetList.value = p
      templateList.value = t
      regexPresetList.value = rp
    } catch {
      message.error('加载预设/模板/正则列表失败')
    } finally {
      loadingBindings.value = false
    }
  }
}, { immediate: true })

function cleanConfig(config: ChatConfig): ChatConfig {
  const result: ChatConfig = {}
  for (const [k, v] of Object.entries(config)) {
    if (v !== null && v !== undefined && v !== '') {
      result[k as keyof ChatConfig] = v as any
    }
  }
  return result
}

async function handleSave() {
  saving.value = true
  try {
    const convId = convStore.currentId
    if (!convId) return

    // ── 1) 三件套绑定（按需 sequential，确保 preset 切换不被后面的 regex 切换 race） ──
    // preset 的 apply 会改 chat_config（合并 sampling/context），如果用户同时改了
    // 数值参数，这里要确保 preset 应用完成后再让 _config 覆盖（顺序：preset→regex→template→config）
    let lastConv = convStore.list.find(c => c.id === convId) || null

    if (bindingsLocal.value.preset_id !== bindingsInitial.value.preset_id) {
      lastConv = await applyPreset(convId, bindingsLocal.value.preset_id)
    }
    if (bindingsLocal.value.regex_preset_id !== bindingsInitial.value.regex_preset_id) {
      lastConv = await switchRegexPreset(convId, bindingsLocal.value.regex_preset_id)
    }
    if (bindingsLocal.value.template_id !== bindingsInitial.value.template_id) {
      lastConv = await switchTemplate(convId, bindingsLocal.value.template_id)
    }

    // ── 2) 剩下四块并发（无相互依赖） ──
    const [cfgResp, wbResp, anResp, togResp] = await Promise.all([
      updateConversationConfig(convId, cleanConfig(localConfig.value)),
      updateConversationWorldbooks(convId, boundIds.value),
      updateConversationAuthorNote(convId, {
        author_note: anLocal.value.author_note || null,
        an_depth: anLocal.value.an_depth,
        an_role: anLocal.value.an_role,
        an_interval: anLocal.value.an_interval,
      }),
      updateConversationToggles(convId, {
        analyze_emotion: togglesLocal.value.analyze_emotion,
      }),
    ])

    const idx = convStore.list.findIndex(c => c.id === convId)
    if (idx !== -1) {
      convStore.list[idx] = {
        ...convStore.list[idx],
        // 绑定三件套：用 lastConv（最后一次绑定切换的响应）拿到的 preset_id/template_id/
        // regex_preset_id/preset_name；以及 reply_length_enabled（switchTemplate 后会变）
        ...(lastConv ? {
          preset_id: lastConv.preset_id,
          preset_name: lastConv.preset_name,
          template_id: lastConv.template_id,
          regex_preset_id: lastConv.regex_preset_id,
          reply_length_enabled: lastConv.reply_length_enabled,
        } : {}),
        // chat_config / effective_chat_config 以 _config 响应为准
        chat_config: cfgResp.chat_config,
        effective_chat_config: cfgResp.effective_chat_config,
        // worldbook_ids 以 _worldbooks 响应为准
        worldbook_ids: wbResp.worldbook_ids,
        // author_note / an_* 以 _author-note 响应为准
        author_note: anResp.author_note,
        an_depth: anResp.an_depth,
        an_role: anResp.an_role,
        an_interval: anResp.an_interval,
        // analyze_emotion 以 _toggles 响应为准
        analyze_emotion: togResp.analyze_emotion,
        updated_at: togResp.updated_at,
      }
    }
    message.success('配置已保存')
    emit('close')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.config-panel { padding: 4px 0; }
.config-title { margin: 0 0 16px; font-size: 18px; }
.params-grid { display: flex; flex-direction: column; gap: 4px; }
.bindings-grid { display: flex; flex-direction: column; gap: 4px; }
.wb-bind { padding: 4px 0; }
.hint { color: var(--color-text-tertiary); font-size: 12px; margin: 6px 0 0; }
.switch-hint { color: var(--color-text-tertiary); font-size: 12px; margin-left: 8px; line-height: 1.5; }
.config-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px; }
.empty-vars { color: var(--color-text-tertiary); font-size: 13px; padding: 12px 0; }
.vars-table {
  display: flex; flex-direction: column;
  border: 1px solid var(--color-border, #eee);
  border-radius: 6px;
  margin-top: 8px;
  max-height: 280px;
  overflow-y: auto;
}
.vars-row {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 12px;
  padding: 6px 10px;
  font-size: 13px;
  border-bottom: 1px solid var(--color-border, #f0f0f0);
}
.vars-row:last-child { border-bottom: 0; }
.vars-head { background: var(--color-bg-page, #fafafa); font-weight: 600; color: var(--color-text-tertiary); font-size: 12px; }
.vars-key, .vars-val {
  font-family: 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.vars-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.mvu-state {
  border: 1px solid var(--color-border, #eee);
  border-radius: 6px;
  padding: 8px 10px;
  margin-top: 8px;
  background: var(--color-bg-surface-elevated, #fafafa);
}
.mvu-state-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.mvu-warning {
  margin: 6px 0 0;
  color: #d03050;
  font-size: 12px;
}
.mvu-runtime {
  border: 1px solid var(--color-border, #eee);
  border-radius: 6px;
  padding: 8px 10px;
  margin-top: 8px;
  background: var(--color-bg-surface-elevated, #fafafa);
}
.mvu-runtime-head {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 12px; font-weight: 600; color: var(--color-text-secondary);
}
.mvu-runtime-counts { display: flex; gap: 8px; font-weight: 400; }
.mvu-runtime-list { list-style: none; margin: 6px 0 0; padding: 0; }
.mvu-runtime-list li {
  display: flex; gap: 8px; align-items: baseline;
  font-size: 12px; padding: 2px 0;
}
.mvu-role {
  flex: none; min-width: 44px;
  color: #2080f0; font-family: monospace;
}
.mvu-comment {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--color-text-secondary);
}
.mvu-chars { flex: none; color: var(--color-text-tertiary); }
.mvu-update {
  border-top: 1px solid var(--color-border, #eee);
  margin-top: 8px;
  padding-top: 8px;
}
.mvu-update-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.mvu-update-channel {
  font-family: 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  border: 1px solid var(--color-border, #ddd);
  border-radius: 4px;
  padding: 1px 6px;
}
.mvu-update-channel.is-tool { color: #18a058; border-color: #18a058; }
.mvu-update-channel.is-text { color: #2080f0; border-color: #2080f0; }
.mvu-update-channel.is-none { color: #d03050; border-color: #d03050; }
.mvu-update-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-family: 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
}
.mvu-update-details {
  margin-top: 6px;
  font-size: 11px;
  color: var(--color-text-secondary);
}
.mvu-update-details summary { cursor: pointer; }
.mvu-update-details p { margin: 3px 0; word-break: break-all; }
.mvu-diag {
  margin: 6px 0 0; font-size: 11px; line-height: 1.5;
  color: var(--color-text-tertiary);
}
</style>
