<template>
  <PageShell maxWidth="800px">
    <WorkspaceHeader
      eyebrow="创作资产"
      :title="isEdit ? `编辑「${form.name || '...'}」` : '新建预设'"
      backTo="/presets"
      backLabel="所有预设"
    />

    <div class="form-wrapper">
      <n-spin :show="loadingForm">
        <n-form ref="formRef" :model="form" :rules="rules" label-placement="top" size="large">
          <n-form-item path="name" label="预设名称">
            <n-input v-model:value="form.name" placeholder="预设名称" />
          </n-form-item>

          <n-form-item label="描述">
            <n-input v-model:value="form.description" type="textarea" placeholder="预设描述..." :rows="2" />
          </n-form-item>

          <n-tabs type="line" v-model:value="activeTab">
            <!-- Tab 1: 采样参数 -->
            <n-tab-pane name="sampling" tab="采样参数">
              <div class="params-grid">
                <n-form-item label="Temperature">
                  <n-input-number v-model:value="form.sampling_params.temperature" :min="0" :max="2" :step="0.05" />
                </n-form-item>
                <n-form-item label="Top P">
                  <n-input-number v-model:value="form.sampling_params.top_p" :min="0" :max="1" :step="0.01" />
                </n-form-item>
                <n-form-item label="Top K">
                  <n-input-number v-model:value="form.sampling_params.top_k" :min="0" :max="200" :step="1" />
                </n-form-item>
                <n-form-item label="Min P">
                  <n-input-number v-model:value="form.sampling_params.min_p" :min="0" :max="1" :step="0.01" />
                </n-form-item>
                <n-form-item label="Frequency Penalty">
                  <n-input-number v-model:value="form.sampling_params.frequency_penalty" :min="-2" :max="2" :step="0.01" />
                </n-form-item>
                <n-form-item label="Presence Penalty">
                  <n-input-number v-model:value="form.sampling_params.presence_penalty" :min="-2" :max="2" :step="0.01" />
                </n-form-item>
                <n-form-item label="Repetition Penalty">
                  <n-input-number v-model:value="form.sampling_params.repetition_penalty" :min="1" :max="2" :step="0.01" />
                </n-form-item>
              </div>
              <n-button size="small" dashed @click="clearSamplingParams">清除采样参数</n-button>
            </n-tab-pane>

            <!-- Tab 2: 上下文设置 -->
            <n-tab-pane name="context" tab="上下文设置">
              <div class="params-grid">
                <n-form-item label="上下文窗口 Token">
                  <n-input-number v-model:value="form.context_settings.openai_max_context" :min="1000" :max="2000000" :step="1000" />
                </n-form-item>
                <n-form-item label="最大输出 Token">
                  <n-input-number v-model:value="form.context_settings.openai_max_tokens" :min="256" :max="131072" :step="256" />
                </n-form-item>
              </div>
              <n-button size="small" dashed @click="clearContextSettings">清除上下文设置</n-button>
            </n-tab-pane>

            <!-- Tab 3: Prompts -->
            <n-tab-pane name="prompts" tab="Prompts">
              <div class="prompts-section">
                <div class="prompts-header">
                  <span>提示词列表 ({{ form.prompts.length }})</span>
                  <n-button size="small" @click="addPrompt">+ 添加 Prompt</n-button>
                </div>

                <div class="prompt-list">
                  <div v-for="(p, idx) in form.prompts" :key="idx" :class="['prompt-card', { 'prompt-disabled': !p.enabled }]">
                    <div class="prompt-card-header">
                      <div class="prompt-move">
                        <n-button size="tiny" text :disabled="idx === 0" @click="movePrompt(idx, -1)">
                          <n-icon><ChevronUp /></n-icon>
                        </n-button>
                        <n-button size="tiny" text :disabled="idx === form.prompts.length - 1" @click="movePrompt(idx, 1)">
                          <n-icon><ChevronDown /></n-icon>
                        </n-button>
                      </div>
                      <n-switch v-model:value="p.enabled" size="small" />
                      <n-input v-model:value="p.name" placeholder="名称" size="small" style="flex: 1; min-width: 100px" />
                      <n-select v-model:value="p.role" :options="roleOptions" size="small" style="width: 100px" />
                      <n-button size="tiny" @click="togglePrompt(idx)">
                        <n-icon><CreateOutline /></n-icon>
                      </n-button>
                      <n-button size="tiny" type="error" text @click="removePrompt(idx)">删除</n-button>
                    </div>
                    <div v-if="promptExpanded.has(idx)" class="prompt-card-body">
                      <n-input
                        v-model:value="p.content"
                        type="textarea"
                        placeholder="Prompt 内容..."
                        :rows="5"
                        :autosize="{ minRows: 3, maxRows: 30 }"
                      />
                      <div class="injection-options">
                        <n-form-item label="注入位置" label-placement="left" size="small">
                          <n-select v-model:value="p.injection_position" :options="injectionPositionOptions" size="small" style="width: 180px" />
                        </n-form-item>
                        <n-form-item label="注入深度" label-placement="left" size="small">
                          <n-input-number v-model:value="p.injection_depth" :min="0" :max="20" size="small" style="width: 120px" />
                        </n-form-item>
                        <n-form-item label="排序" label-placement="left" size="small">
                          <n-input-number v-model:value="p.injection_order" :min="0" :max="1000" size="small" style="width: 120px" />
                        </n-form-item>
                        <n-form-item label="标记" label-placement="left" size="small">
                          <n-switch v-model:value="p.marker" size="small" />
                        </n-form-item>
                      </div>
                    </div>
                  </div>

                  <div v-if="form.prompts.length === 0" class="prompts-empty">
                    <n-empty description="暂无 Prompt，系统将使用默认组装逻辑" />
                  </div>
                </div>
              </div>
            </n-tab-pane>

            <!-- Tab 4: Extensions -->
            <n-tab-pane name="extensions" tab="Extensions">
              <n-input
                v-model:value="extensionsText"
                type="textarea"
                placeholder="{}"
                :rows="12"
                :autosize="{ minRows: 6, maxRows: 30 }"
              />
              <p class="tab-hint">Extensions 以 JSON 格式编辑</p>
            </n-tab-pane>
          </n-tabs>

          <div class="form-actions">
            <n-button @click="$router.push('/presets')">取消</n-button>
            <n-button type="primary" :loading="saving" @click="handleSave">保存</n-button>
          </div>
        </n-form>
      </n-spin>
    </div>
  </PageShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NIcon, NSpin, NForm, NFormItem, NInput, NInputNumber, NSelect,
  NTabs, NTabPane, NEmpty, NSwitch, useMessage,
} from 'naive-ui'
import { ArrowBack, ChevronUp, ChevronDown, CreateOutline } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import WorkspaceHeader from '../components/layout/WorkspaceHeader.vue'
import { fetchPresetDetail, updatePreset, createPreset } from '../api/preset'
import type { PromptEntry } from '../types'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const formRef = ref()
const loadingForm = ref(false)
const saving = ref(false)
const activeTab = ref('sampling')
const isEdit = computed(() => !!route.params.id)

const roleOptions = [
  { label: 'system', value: 'system' },
  { label: 'user', value: 'user' },
  { label: 'assistant', value: 'assistant' },
]

const injectionPositionOptions = [
  { label: '相对 (末尾)', value: 0 },
  { label: '绝对 (头部)', value: 1 },
  { label: '聊天历史', value: 2 },
]

const emptyPrompt = (): PromptEntry => ({
  identifier: '',
  name: '',
  role: 'system',
  content: '',
  enabled: true,
  injection_position: 0,
  injection_depth: 4,
  injection_order: 100,
  system_prompt: false,
  marker: false,
  forbid_overrides: false,
})

const form = ref<{
  name: string
  description: string
  sampling_params: Record<string, number | null>
  context_settings: Record<string, number | null>
  prompts: PromptEntry[]
  extensions: Record<string, any>
}>({
  name: '',
  description: '',
  sampling_params: {},
  context_settings: {},
  prompts: [],
  extensions: {},
})

const extensionsText = ref('{}')
const promptExpanded = ref(new Set<number>())

watch(extensionsText, (val) => {
  try {
    form.value.extensions = JSON.parse(val)
  } catch {}
})

const rules = {
  name: [{ required: true, message: '请输入预设名称', trigger: 'blur' }],
}

onMounted(async () => {
  if (isEdit.value) {
    loadingForm.value = true
    try {
      const d = await fetchPresetDetail(route.params.id as string)
      form.value = {
        name: d.name,
        description: d.description || '',
        sampling_params: d.sampling_params ? { ...d.sampling_params } : {},
        context_settings: d.context_settings ? { ...d.context_settings } : {},
        prompts: d.prompts ? d.prompts.map(p => ({ ...p })) : [],
        extensions: d.extensions || {},
      }
      extensionsText.value = JSON.stringify(d.extensions || {}, null, 2)
    } catch {
      message.error('加载预设数据失败')
      router.push('/presets')
    } finally {
      loadingForm.value = false
    }
  }
})

function togglePrompt(idx: number) {
  const s = new Set(promptExpanded.value)
  if (s.has(idx)) s.delete(idx); else s.add(idx)
  promptExpanded.value = s
}

function addPrompt() {
  form.value.prompts.push(emptyPrompt())
}

function removePrompt(idx: number) {
  form.value.prompts.splice(idx, 1)
}

function movePrompt(idx: number, dir: number) {
  const target = idx + dir
  if (target < 0 || target >= form.value.prompts.length) return
  const tmp = form.value.prompts[idx]
  form.value.prompts[idx] = form.value.prompts[target]
  form.value.prompts[target] = tmp
}

function cleanParams(obj: Record<string, any>): Record<string, any> {
  const result: Record<string, any> = {}
  for (const [k, v] of Object.entries(obj)) {
    if (v !== null && v !== undefined && v !== '') result[k] = v
  }
  return result
}

function clearSamplingParams() {
  form.value.sampling_params = {}
}

function clearContextSettings() {
  form.value.context_settings = {}
}

function buildSaveData() {
  return {
    name: form.value.name,
    description: form.value.description || null,
    sampling_params: cleanParams(form.value.sampling_params),
    context_settings: cleanParams(form.value.context_settings),
    prompts: form.value.prompts,
    extensions: form.value.extensions,
  }
}

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch { return }

  saving.value = true
  try {
    const data = buildSaveData()
    if (isEdit.value) {
      await updatePreset(route.params.id as string, data)
      message.success('预设已更新')
    } else {
      await createPreset(data)
      message.success('预设已创建')
    }
    router.push('/presets')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.page-title { flex: 1; margin: 0; font-size: 20px; white-space: nowrap; }
.form-wrapper { background: var(--color-bg-surface); border-radius: var(--radius-lg); padding: 24px; }

.params-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0 16px;
}

.tab-hint { margin: 8px 0 0; font-size: 12px; color: var(--color-text-tertiary); }

.prompts-section { margin-top: 0; }
.prompts-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.prompt-list { display: flex; flex-direction: column; gap: 10px; }
.prompt-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-light);
  border-radius: 8px;
  padding: 12px;
}
.prompt-card-header { display: flex; align-items: center; gap: 8px; }
.prompt-card-body { margin-top: 10px; }
.prompt-move { display: flex; flex-direction: column; gap: 0; }
.prompt-disabled { opacity: 0.5; }
.prompts-empty { padding: 24px 0; }

.injection-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 12px;
}

.form-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px; }
</style>
