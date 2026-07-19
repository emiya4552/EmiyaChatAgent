<template>
  <PageShell>
    <WorkspaceHeader
      eyebrow="创作资产"
      :title="isEdit ? '编辑正则预设' : '新建正则预设'"
      backTo="/regex-presets"
      backLabel="所有正则预设"
    >
      <template #actions>
        <n-button type="primary" :loading="saving" @click="handleSave">保存</n-button>
      </template>
    </WorkspaceHeader>

    <div class="page-content">
      <div class="form-section">
        <div class="form-row">
          <label class="form-label">名称</label>
          <n-input v-model:value="form.name" placeholder="正则预设名称" maxlength="200" />
        </div>
        <div class="form-row">
          <label class="form-label">描述</label>
          <n-input v-model:value="form.description" placeholder="描述（可选）" type="textarea" :rows="2" />
        </div>
      </div>

      <div class="section-header">
        <h3>正则脚本</h3>
        <n-button size="small" type="primary" @click="addScript">+ 添加脚本</n-button>
      </div>

      <div v-if="form.scripts.length === 0" class="empty-scripts">
        <n-empty description="暂无正则脚本，点击上方按钮添加" />
      </div>

      <div v-else class="scripts-table">
        <div v-for="(s, idx) in form.scripts" :key="s._key" class="script-row">
          <div class="script-row-header">
            <span class="script-index">#{{ idx + 1 }}</span>
            <n-input v-model:value="s.scriptName" placeholder="脚本名称" size="small" class="script-name" />

            <!-- 启用开关：绿色=启用，灰色=禁用（符合直觉） -->
            <div class="toggle-cell">
              <span class="toggle-label">启用</span>
              <n-switch
                :value="!s.disabled"
                size="small"
                @update:value="(v: boolean) => (s.disabled = !v)"
              />
            </div>

            <!-- 作用阶段：Prompt（送 LLM 前） vs Reply（渲染时） -->
            <div class="toggle-cell">
              <span class="toggle-label">作用于</span>
              <n-switch v-model:value="s.promptOnly" size="small">
                <template #checked>Prompt</template>
                <template #unchecked>Reply</template>
              </n-switch>
              <n-popover trigger="click" placement="top" :width="320">
                <template #trigger>
                  <n-icon class="help-icon"><HelpCircleOutline /></n-icon>
                </template>
                <div class="help-text">
                  正则脚本可以应用在两个独立的阶段：
                  <ul>
                    <li><b>Prompt</b>：在<b>把上下文发送给 LLM 之前</b>跑（对应 ST 的 <code>promptOnly</code>）。常用于剔除历史楼里不该让 AI 再看的标记，或清洗 AI 八股。<b>发出去的字符串变了</b>，但用户在聊天界面看到的原文不变。</li>
                    <li><b>Reply</b>：在<b>渲染到聊天界面之前</b>跑（对应 ST 的 <code>markdownOnly</code>）。常用于把 AI 输出里的占位符替换成漂亮的 HTML 状态栏，或折叠变量更新块。<b>UI 显示变了</b>，但发给 AI 的字符串不变。</li>
                  </ul>
                </div>
              </n-popover>
            </div>

            <n-button text type="error" size="small" @click="removeScript(idx)">
              <template #icon><n-icon><TrashOutline /></n-icon></template>
            </n-button>
          </div>
          <div class="script-row-fields">
            <div class="field">
              <label>匹配正则</label>
              <n-input v-model:value="s.findRegex" placeholder="/pattern/flags" size="small" />
            </div>
            <div class="field">
              <label>替换为</label>
              <n-input v-model:value="s.replaceString" placeholder="替换字符串" size="small" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </PageShell>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NIcon, NInput, NSwitch, NEmpty, NPopover, useMessage } from 'naive-ui'
import { ArrowBack, TrashOutline, HelpCircleOutline } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import WorkspaceHeader from '../components/layout/WorkspaceHeader.vue'
import { fetchRegexPresetDetail, createRegexPreset, updateRegexPreset } from '../api/regexPreset'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const isEdit = !!route.params.id
const saving = ref(false)

interface ScriptForm {
  _key: number
  scriptName: string
  findRegex: string
  replaceString: string
  disabled: boolean
  promptOnly: boolean
  placement: number[]
}

const form = ref({
  name: '',
  description: '',
  scripts: [] as ScriptForm[],
})

let keyCounter = 0
function addScript() {
  form.value.scripts.push({
    _key: ++keyCounter,
    scriptName: '',
    findRegex: '/pattern/g',
    replaceString: '',
    disabled: false,
    promptOnly: true,
    placement: [2],
  })
}

function removeScript(idx: number) {
  form.value.scripts.splice(idx, 1)
}

onMounted(async () => {
  if (isEdit) {
    try {
      const detail = await fetchRegexPresetDetail(route.params.id as string)
      form.value.name = detail.name
      form.value.description = detail.description || ''
      form.value.scripts = detail.scripts.map(s => ({
        _key: ++keyCounter,
        scriptName: s.scriptName || '',
        findRegex: s.findRegex || '',
        replaceString: s.replaceString || '',
        disabled: s.disabled ?? false,
        promptOnly: s.promptOnly ?? true,
        placement: s.placement || [2],
      }))
    } catch (err: any) {
      message.error(err.response?.data?.detail || '加载失败')
      router.push('/regex-presets')
    }
  }
})

async function handleSave() {
  if (!form.value.name.trim()) {
    message.warning('请输入名称')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.value.name,
      description: form.value.description || null,
      scripts: form.value.scripts.map(({ _key, ...rest }) => rest),
    }
    if (isEdit) {
      await updateRegexPreset(route.params.id as string, payload)
    } else {
      await createRegexPreset(payload as any)
    }
    message.success('保存成功')
    router.push('/regex-presets')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.page-title { flex: 1; margin: 0; font-size: 20px; }
.page-content { max-width: 900px; margin: 0 auto; }
.form-section { background: var(--color-bg-surface); border-radius: var(--radius-md); padding: 20px 24px; margin-bottom: 20px; }
.form-row { margin-bottom: 14px; }
.form-label { display: block; margin-bottom: 4px; font-weight: 600; font-size: 14px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 16px; }
.empty-scripts { padding: 40px 0; }
.scripts-table { display: flex; flex-direction: column; gap: 10px; }
.script-row {
  background: var(--color-bg-surface); border-radius: var(--radius-md);
  padding: 14px 18px; box-shadow: var(--shadow-sm);
}
.script-row-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.script-index { font-weight: 600; color: var(--color-text-tertiary); font-size: 13px; min-width: 30px; }
.script-name { flex: 1; max-width: 240px; }
.script-row-fields { display: flex; gap: 12px; }
.script-row-fields .field { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.script-row-fields .field label { font-size: 12px; color: var(--color-text-tertiary); }
.toggle-cell { display: flex; align-items: center; gap: 6px; }
.toggle-label { font-size: 12px; color: var(--color-text-tertiary); }
.help-icon {
  cursor: pointer;
  color: var(--color-text-tertiary);
  font-size: 14px;
  transition: color var(--transition-fast);
}
.help-icon:hover { color: var(--color-primary); }
.help-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-primary);
  white-space: normal;
}
.help-text :deep(ul) { margin: 6px 0 0; padding-left: 20px; }
.help-text :deep(li) { margin-bottom: 6px; }
.help-text :deep(code) {
  background: var(--color-bg-hover, rgba(0,0,0,0.05)); padding: 1px 5px; border-radius: 3px;
  font-size: 12px; font-family: 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
}
.help-text :deep(b) { color: var(--color-text-primary); }
</style>
