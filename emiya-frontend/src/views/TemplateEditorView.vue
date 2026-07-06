<template>
  <PageShell maxWidth="900px">
    <div class="page-header">
      <n-button text @click="$router.push('/templates')">
        <template #icon><n-icon><ArrowBack /></n-icon></template>
        返回
      </n-button>
      <h2 class="page-title">
        {{ isReadOnly ? '查看：系统默认（内置）' : (isEdit ? '编辑模板' : '新建模板') }}
      </h2>
    </div>

    <n-alert v-if="isReadOnly" type="warning" class="readonly-banner" :show-icon="true">
      此为系统内置默认模板，随版本更新；不可编辑。要个性化，请去模板列表点"复制为我的模板"。
    </n-alert>

    <n-spin :show="loading">
      <div class="editor-layout">
        <!-- 模板基本信息 -->
        <n-card title="基本信息" class="section-card">
          <n-form-item label="名称">
            <n-input v-model:value="form.name" placeholder="模板名称" :disabled="isReadOnly" />
          </n-form-item>
          <n-form-item label="描述">
            <n-input v-model:value="form.description" placeholder="模板描述（可选）" :disabled="isReadOnly" />
          </n-form-item>
          <n-form-item v-if="!isReadOnly" label="设为首选">
            <n-switch v-model:value="form.is_default" />
            <span class="switch-hint">新会话默认使用此模板</span>
          </n-form-item>
        </n-card>

        <!-- 可用组件面板 -->
        <n-card title="Prompt 块列表" class="section-card">
          <template v-if="!isReadOnly" #header-extra>
            <n-dropdown trigger="click" :options="addBlockOptions" @select="onAddBlock">
              <n-button size="small" type="primary">添加块</n-button>
            </n-dropdown>
          </template>

          <n-alert type="info" class="blocks-explainer" :show-icon="true">
            <strong>每个块右上的开关</strong>=对话里对应功能的开关：
            <ul class="blocks-explainer-list">
              <li><code>dynamic</code> 块（记忆 / 关系 / 画像 / 摘要 / 约束）：关掉就跳过相关后端节点（不查 ChromaDB、不调 LLM 评估等）</li>
              <li><code>reply_length</code> 块：关掉时聊天页右上的<strong>短/中/长按钮组会被禁用</strong>（详见 ADR-0014）</li>
              <li><code>mes_example</code> / <code>author_note</code> / <code>outlet</code> / 静态 / 变量块：关掉则该块不参与 prompt 拼接</li>
            </ul>
            想关闭某项功能时，<strong>不必另设开关</strong>——直接关掉对应块即可（情感分析除外：情绪+好感度感知没有模板块，独立放在对话设置面板；见 ADR-0019）。
          </n-alert>

          <div v-if="form.blocks.length === 0" class="empty-hint">
            暂未添加任何 Prompt 块。点击"添加块"开始。
          </div>

          <div v-for="(block, idx) in form.blocks" :key="block.id" class="block-item">
            <div class="block-header">
              <div v-if="!isReadOnly" class="block-drag">
                <n-button text size="tiny" :disabled="idx === 0" @click="moveBlock(idx, -1)">
                  <n-icon><ChevronUp /></n-icon>
                </n-button>
                <n-button text size="tiny" :disabled="idx === form.blocks.length - 1" @click="moveBlock(idx, 1)">
                  <n-icon><ChevronDown /></n-icon>
                </n-button>
              </div>
              <n-tag :type="blockTypeColor(block.type)" size="small">{{ blockTypeLabel(block.type) }}</n-tag>
              <span class="block-label">{{ block.label }}</span>
              <n-switch v-model:value="block.enabled" size="small" :disabled="isReadOnly" />
              <n-button v-if="!isReadOnly" text size="tiny" type="error" @click="removeBlock(idx)">
                <n-icon><Close /></n-icon>
              </n-button>
            </div>

            <div class="block-body" v-if="block.enabled">
              <n-form-item label="标签">
                <n-input v-model:value="block.label" size="small" :disabled="isReadOnly" />
              </n-form-item>

              <!-- Static block -->
              <template v-if="block.type === 'static'">
                <n-form-item label="内容">
                  <n-input v-model:value="block.content" type="textarea" :rows="3" size="small"
                    placeholder="输入文本，使用 {{persona.name}} 等变量" :disabled="isReadOnly" />
                </n-form-item>
                <div v-if="!isReadOnly" class="var-hints">
                  可用变量：
                  <n-button text size="tiny" @click="insertVar(idx, 'persona.name')"><code v-text="'{{persona.name}}'"></code></n-button>
                  <n-button text size="tiny" @click="insertVar(idx, 'persona.personality')"><code v-text="'{{persona.personality}}'"></code></n-button>
                  <n-button text size="tiny" @click="insertVar(idx, 'persona.background')"><code v-text="'{{persona.background}}'"></code></n-button>
                  <n-button text size="tiny" @click="insertVar(idx, 'persona.speaking_style')"><code v-text="'{{persona.speaking_style}}'"></code></n-button>
                  <n-button text size="tiny" @click="insertVar(idx, 'persona.age')"><code v-text="'{{persona.age}}'"></code></n-button>
                  <n-button text size="tiny" @click="insertVar(idx, 'persona.gender')"><code v-text="'{{persona.gender}}'"></code></n-button>
                </div>
              </template>

              <!-- Variable block -->
              <template v-if="block.type === 'variable'">
                <n-form-item label="变量引用">
                  <n-select v-model:value="block.variable_ref" :options="variableOptions" size="small" :disabled="isReadOnly" />
                </n-form-item>
              </template>

              <!-- Dynamic block -->
              <template v-if="block.type === 'dynamic'">
                <n-form-item label="动态内容源">
                  <n-select v-model:value="block.dynamic_ref" :options="dynamicOptions" size="small" :disabled="isReadOnly" />
                </n-form-item>
                <p class="block-hint">此块由 LLM 在每轮对话时自动生成</p>
              </template>

              <!-- mes_example block -->
              <template v-if="block.type === 'mes_example'">
                <p class="block-hint">从当前 AI 角色卡的 mes_example 字段解析 user/assistant 对话对（按 &lt;START&gt; 分隔）；首条会被打上 EM 锚点，世界书 EM_TOP/EM_BOTTOM 位置的条目围绕它注入</p>
              </template>

              <!-- Reply length block -->
              <template v-if="block.type === 'reply_length' && block.reply_length_config">
                <n-form-item label="短回复提示">
                  <n-input v-model:value="block.reply_length_config.short" type="textarea" :rows="2" size="small" :disabled="isReadOnly" />
                </n-form-item>
                <n-form-item label="中等回复 (留空=无提示)">
                  <n-input v-model:value="block.reply_length_config.medium" size="small" :disabled="isReadOnly" />
                </n-form-item>
                <n-form-item label="长回复提示">
                  <n-input v-model:value="block.reply_length_config.long" type="textarea" :rows="2" size="small" :disabled="isReadOnly" />
                </n-form-item>
              </template>

              <!-- Outlet block (世界书具名插槽) -->
              <template v-if="block.type === 'outlet'">
                <n-form-item label="Outlet 名称">
                  <n-input v-model:value="block.outlet_name" size="small"
                    placeholder="对应世界书条目 position=OUTLET 时的 outlet_name" :disabled="isReadOnly" />
                </n-form-item>
                <p class="block-hint">渲染时会收集所有 outlet_name 匹配的激活世界书条目内容拼接为本块内容</p>
              </template>

              <!-- Author's Note block -->
              <template v-if="block.type === 'author_note'">
                <p class="block-hint">内容由对话级 author_note 字段提供（在对话设置面板编辑）；本块用于决定 AN 在 Prompt 中的位置和启停</p>
              </template>
            </div>
          </div>
        </n-card>

        <div v-if="!isReadOnly" class="form-actions">
          <n-button @click="$router.push('/templates')">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleSave">保存</n-button>
        </div>
        <div v-else class="form-actions">
          <n-button @click="$router.push('/templates')">返回</n-button>
        </div>
      </div>
    </n-spin>
  </PageShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NAlert, NButton, NIcon, NSpin, NCard, NFormItem, NInput, NInputNumber,
  NSelect, NSwitch, NTag, NDropdown, useMessage,
} from 'naive-ui'
import { ArrowBack, ChevronUp, ChevronDown, Close } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import { fetchTemplate, createTemplate, updateTemplate, fetchDefaultPreview } from '../api/template'
import type { PromptBlock, TemplateDetail } from '../types'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const isEdit = computed(() => !!route.params.id)
// 只读模式：路由是 /templates/default-view（查看内置默认模板）
const isReadOnly = computed(() => route.name === 'template-default-view')

let blockCounter = 0

function newBlock(type: PromptBlock['type']): PromptBlock {
  const id = `block_${Date.now()}_${blockCounter++}`
  const base: PromptBlock = {
    id,
    type,
    label: '',
    enabled: true,
    role: 'system',
    content: null,
    variable_ref: null,
    dynamic_ref: null,
    reply_length_config: null,
    outlet_name: null,
  }
  if (type === 'static') {
    base.label = '静态文本'
    base.content = ''
  } else if (type === 'variable') {
    base.label = '变量'
    base.variable_ref = 'persona.name'
  } else if (type === 'dynamic') {
    base.label = '动态内容'
    base.dynamic_ref = 'memories'
  } else if (type === 'reply_length') {
    base.label = '回复长度'
    base.reply_length_config = { short: '', medium: '', long: '' }
  } else if (type === 'outlet') {
    base.label = '世界书具名插槽'
    base.outlet_name = ''
  } else if (type === 'author_note') {
    base.label = '作者笔记 AN'
  } else if (type === 'mes_example') {
    base.label = '对话示例'
  }
  return base
}

const form = ref<{
  name: string
  description: string | null
  is_default: boolean
  blocks: PromptBlock[]
}>({
  name: '',
  description: null,
  is_default: false,
  blocks: [],
})

const variableOptions = [
  { label: 'persona.name (名称)', value: 'persona.name' },
  { label: 'persona.personality (性格)', value: 'persona.personality' },
  { label: 'persona.background (背景)', value: 'persona.background' },
  { label: 'persona.speaking_style (说话风格)', value: 'persona.speaking_style' },
  { label: 'persona.age (年龄)', value: 'persona.age' },
  { label: 'persona.gender (性别)', value: 'persona.gender' },
  { label: 'persona.quirks (癖好)', value: 'persona.quirks' },
  { label: 'persona.constraints (约束)', value: 'persona.constraints' },
]

const dynamicOptions = [
  // 'emotion' 已移除（详见 docs/adr/0005）：情绪不再注入 Prompt
  { label: '当前关系', value: 'relationship' },
  { label: '记忆', value: 'memories' },
  { label: '用户画像', value: 'profile' },
  { label: '对话摘要', value: 'summary' },
  { label: '交互约束', value: 'constraints' },
]

const addBlockOptions = computed(() => [
  { label: '静态文本', key: 'static' },
  { label: '变量引用', key: 'variable' },
  { label: '动态内容 (关系/记忆/画像/摘要)', key: 'dynamic' },
  { label: '回复长度控制', key: 'reply_length' },
  { label: '对话示例 (mes_example)', key: 'mes_example' },
  { label: '世界书具名插槽 (outlet)', key: 'outlet' },
  { label: '作者笔记 (author_note)', key: 'author_note' },
])

function blockTypeColor(type: string): 'info' | 'success' | 'warning' | 'error' | 'default' {
  const map: Record<string, 'info' | 'success' | 'warning' | 'error' | 'default'> = {
    static: 'info',
    variable: 'success',
    dynamic: 'warning',
    reply_length: 'default',
    mes_example: 'warning',
    outlet: 'success',
    author_note: 'info',
  }
  return map[type] || 'default'
}

function blockTypeLabel(type: string) {
  const map: Record<string, string> = {
    static: '静态',
    variable: '变量',
    dynamic: '动态',
    reply_length: '长度',
    mes_example: '示例',
    outlet: 'outlet',
    author_note: 'AN',
  }
  return map[type] || type
}

function onAddBlock(key: string) {
  form.value.blocks.push(newBlock(key as PromptBlock['type']))
}

function removeBlock(idx: number) {
  form.value.blocks.splice(idx, 1)
}

function moveBlock(idx: number, dir: number) {
  const target = idx + dir
  if (target < 0 || target >= form.value.blocks.length) return
  const tmp = form.value.blocks[target]
  form.value.blocks[target] = form.value.blocks[idx]
  form.value.blocks[idx] = tmp
}

function insertVar(idx: number, varName: string) {
  const block = form.value.blocks[idx]
  if (block.type === 'static') {
    block.content = (block.content || '') + `{{${varName}}}`
  }
}

onMounted(async () => {
  if (isReadOnly.value) {
    loading.value = true
    try {
      const preview = await fetchDefaultPreview()
      form.value = {
        name: preview.name,
        description: preview.description,
        is_default: false,
        blocks: preview.blocks.map((b: any) => ({
          ...b,
          reply_length_config: b.reply_length_config || { short: '', medium: '', long: '' },
          outlet_name: b.outlet_name ?? null,
        })),
      }
    } catch {
      message.error('加载内置默认模板失败')
      router.push('/templates')
    } finally {
      loading.value = false
    }
    return
  }

  if (isEdit.value) {
    loading.value = true
    try {
      const t = await fetchTemplate(route.params.id as string)
      form.value = {
        name: t.name,
        description: t.description,
        is_default: t.is_default,
        blocks: t.blocks.map((b: any) => ({
          ...b,
          reply_length_config: b.reply_length_config || { short: '', medium: '', long: '' },
          outlet_name: b.outlet_name ?? null,
        })),
      }
    } catch {
      message.error('加载模板失败')
      router.push('/templates')
    } finally {
      loading.value = false
    }
  }
})

async function handleSave() {
  if (!form.value.name.trim()) {
    message.warning('请输入模板名称')
    return
  }
  saving.value = true
  try {
    if (isEdit.value) {
      await updateTemplate(route.params.id as string, form.value)
      message.success('模板已更新')
    } else {
      await createTemplate(form.value as any)
      message.success('模板已创建')
    }
    router.push('/templates')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
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
.page-title { flex: 1; margin: 0; font-size: 20px; }
.readonly-banner { margin-bottom: 16px; }
.editor-layout { display: flex; flex-direction: column; gap: 16px; }
.section-card { border-radius: var(--radius-md); }
.switch-hint { margin-left: 8px; font-size: 13px; color: var(--color-text-tertiary); }
.empty-hint { color: var(--color-text-placeholder); padding: 20px; text-align: center; }

.block-item {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
  padding: 8px 12px;
}
.block-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.block-drag { display: flex; flex-direction: column; }
.block-label { flex: 1; font-size: 14px; font-weight: 500; }
.block-body {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border-light);
}
.block-hint { font-size: 12px; color: var(--color-text-tertiary); margin: 0; }
.var-hints { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px; }
.blocks-explainer { margin-bottom: 12px; }
.blocks-explainer-list { margin: 6px 0 6px 18px; padding: 0; line-height: 1.7; }
.blocks-explainer code {
  background: rgba(0, 0, 0, 0.06);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 0;
}
</style>
