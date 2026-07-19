<template>
  <PageShell maxWidth="680px">
    <WorkspaceHeader
      eyebrow="创作资产"
      :title="isEdit ? `编辑「${form.name || '...'}」` : '创建角色卡'"
      backTo="/personas"
      backLabel="所有角色"
    />

    <div class="form-wrapper">
      <n-spin :show="loadingForm">
        <n-form ref="formRef" :model="form" :rules="rules" label-placement="top" size="large">
          <n-form-item path="name" label="名称">
            <n-input v-model:value="form.name" placeholder="角色名称" />
          </n-form-item>

          <n-form-item path="personality" label="性格描述">
            <n-input v-model:value="form.personality" type="textarea" placeholder="描述性格特征..." :rows="4" />
          </n-form-item>

          <n-form-item label="背景故事">
            <n-input v-model:value="form.background" type="textarea" placeholder="角色的背景故事/出身（区别于「场景」）..." :rows="4" />
          </n-form-item>

          <n-form-item label="场景 (Scenario)">
            <n-input
              v-model:value="form.scenario"
              type="textarea"
              placeholder="角色当前所处的情境（例：在咖啡馆打工 / 星舰甲板上）"
              :rows="2"
            />
          </n-form-item>

          <n-form-item label="开场白">
            <n-input v-model:value="form.first_message" type="textarea" placeholder="新建对话时角色说的第一句话..." :rows="2" />
          </n-form-item>

          <n-form-item label="备用开场白">
            <div class="alt-greetings">
              <div v-if="!form.alternate_greetings.length" class="alt-empty">暂无备用开场白</div>
              <div
                v-for="(g, i) in form.alternate_greetings"
                :key="i"
                class="alt-item"
              >
                <div class="alt-head">
                  <span class="alt-tag">#{{ i + 1 }}</span>
                  <n-button text size="small" @click="removeGreeting(i)">移除</n-button>
                </div>
                <n-input
                  v-model:value="form.alternate_greetings[i]"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                  placeholder="另一个切入场景的开场白..."
                />
              </div>
              <n-button dashed block @click="addGreeting">+ 增加备用开场白</n-button>
            </div>
          </n-form-item>

          <n-form-item label="对话示例 (mes_example)">
            <n-input v-model:value="form.mes_example" type="textarea" placeholder="{{char}}: 角色的示例回复&#10;{{user}}: 用户的示例消息" :rows="4" />
          </n-form-item>

          <n-form-item label="标签">
            <n-dynamic-tags v-model:value="form.tags" placeholder="如：治愈、温柔、咖啡馆" />
          </n-form-item>

          <n-form-item label="默认携带世界书">
            <n-select
              v-model:value="form.default_worldbook_ids"
              multiple
              :options="wbOptions"
              :loading="loadingWb"
              placeholder="新建对话时自动绑定（之后可在对话设置中改动）"
            />
          </n-form-item>

          <n-form-item label="默认 Author's Note">
            <n-input
              v-model:value="form.author_note"
              type="textarea"
              placeholder="新建对话时复制为该对话的初始 AN（之后可改动）"
              :rows="3"
            />
          </n-form-item>

          <n-form-item label="角色卡 CSS 主题">
            <n-input
              v-model:value="form.css_theme"
              type="textarea"
              :autosize="{ minRows: 4, maxRows: 16 }"
              placeholder="/* 卡作者自带的样式包；导入时会从 extensions.css / extensions.style / creator_notes 抽取。
   会在用户级主题之后注入（CSS cascade 覆盖用户级）。详见 ADR-0008 */"
              class="css-input"
            />
          </n-form-item>

          <div class="form-actions">
            <n-button @click="$router.push('/personas')">取消</n-button>
            <n-button type="primary" :loading="saving" @click="handleSave">保存</n-button>
          </div>
        </n-form>
      </n-spin>
    </div>
  </PageShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NIcon, NSpin, NForm, NFormItem, NInput, NDynamicTags, NSelect, useMessage,
} from 'naive-ui'
import { ArrowBack } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import WorkspaceHeader from '../components/layout/WorkspaceHeader.vue'
import { createPersona, updatePersona, fetchPersonaDetail } from '../api/persona'
import { fetchWorldbooks } from '../api/worldbook'
import type { PersonaDetail, WorldbookListItem } from '../types'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const formRef = ref()
const loadingForm = ref(false)
const saving = ref(false)
const isEdit = computed(() => !!route.params.id)

const form = ref({
  name: '',
  personality: '',
  background: '' as string | null,
  scenario: '' as string | null,
  first_message: '' as string | null,
  alternate_greetings: [] as string[],
  mes_example: '' as string | null,
  tags: [] as string[],
  default_worldbook_ids: [] as string[],
  author_note: '' as string | null,
  css_theme: '' as string | null,
})

function addGreeting() {
  form.value.alternate_greetings.push('')
}

function removeGreeting(idx: number) {
  form.value.alternate_greetings.splice(idx, 1)
}

const wbList = ref<WorldbookListItem[]>([])
const loadingWb = ref(false)
const wbOptions = computed(() =>
  wbList.value.map(w => ({
    label: `${w.name}${w.is_template ? ' (模板)' : ''}`,
    value: w.id,
  }))
)

const rules = {
  name: [
    { required: true, message: '请输入名称', trigger: 'blur' },
  ],
}

onMounted(async () => {
  loadingWb.value = true
  try {
    wbList.value = await fetchWorldbooks()
  } catch {
    // 失败不致命，留空 list
  } finally {
    loadingWb.value = false
  }

  if (isEdit.value) {
    loadingForm.value = true
    try {
      const d = await fetchPersonaDetail(route.params.id as string)
      form.value = {
        name: d.name,
        personality: d.personality,
        background: d.background,
        scenario: d.scenario,
        first_message: d.first_message,
        alternate_greetings: d.alternate_greetings || [],
        mes_example: d.mes_example,
        tags: d.tags || [],
        default_worldbook_ids: d.default_worldbook_ids || [],
        author_note: d.author_note,
        css_theme: d.css_theme,
      }
    } catch (err: any) {
      message.error('加载角色卡数据失败')
      router.push('/personas')
    } finally {
      loadingForm.value = false
    }
  }
})

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch { return }

  saving.value = true
  try {
    const data: Record<string, any> = {}
    for (const [key, val] of Object.entries(form.value)) {
      // 空数组对于 default_worldbook_ids 是有意义的（"清空默认书"），保留为 []
      if (key === 'default_worldbook_ids') {
        data[key] = val
        continue
      }
      // alternate_greetings 同理：空列表 = 该角色卡无备用开场白，保留为 []
      if (key === 'alternate_greetings') {
        data[key] = (val as string[]).map(s => (s || '').trim()).filter(Boolean)
        continue
      }
      if (val === '' || val === null) {
        data[key] = null
      } else if (Array.isArray(val) && val.length === 0) {
        data[key] = null
      } else {
        data[key] = val
      }
    }

    if (isEdit.value) {
      await updatePersona(route.params.id as string, data)
      message.success('角色卡已更新')
    } else {
      await createPersona(data as any)
      message.success('角色卡已创建')
    }
    router.push('/personas')
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
.page-title { flex: 1; margin: 0; font-size: 20px; white-space: nowrap; }
.form-wrapper { background: var(--color-bg-surface); border-radius: var(--radius-lg); padding: 24px; }
.form-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px; }

.css-input :deep(textarea) {
  font-family: 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
}
.alt-greetings { display: flex; flex-direction: column; gap: 10px; width: 100%; }
.alt-empty { color: var(--color-text-muted, #888); font-size: 13px; }
.alt-item {
  border: 1px solid var(--color-border, #eee);
  border-radius: var(--radius-md, 6px);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.alt-head { display: flex; justify-content: space-between; align-items: center; }
.alt-tag { font-size: 12px; color: var(--color-text-muted, #888); }
</style>
