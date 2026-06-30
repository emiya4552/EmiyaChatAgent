<template>
  <PageShell maxWidth="1100px">
    <div class="page-header">
      <n-button text @click="$router.push('/chat')">
        <template #icon><n-icon><ArrowBack /></n-icon></template>
        返回聊天
      </n-button>
      <h2 class="page-title">情绪仪表盘</h2>
      <n-button-group>
        <n-button :type="days === 7 ? 'primary' : 'default'" :disabled="isSingleConvMode" @click="switchDays(7)">7天</n-button>
        <n-button :type="days === 30 ? 'primary' : 'default'" :disabled="isSingleConvMode" @click="switchDays(30)">30天</n-button>
      </n-button-group>
    </div>

    <!-- Filter 顶栏：persona + conv 级联 -->
    <div class="filter-bar">
      <div class="filter-item">
        <label class="filter-label">角色</label>
        <n-select
          v-model:value="personaId"
          :options="personaOptions"
          :loading="loadingPersonas"
          placeholder="全部角色"
          clearable
          style="width: 220px"
          @update:value="onPersonaChange"
        />
      </div>
      <div class="filter-item">
        <label class="filter-label">对话</label>
        <n-tooltip :disabled="!!personaId" trigger="hover">
          <template #trigger>
            <div class="conv-wrapper">
              <n-select
                v-model:value="conversationId"
                :options="conversationOptions"
                :loading="loadingConvs"
                :disabled="!personaId"
                placeholder="全部对话"
                clearable
                style="width: 280px"
                @update:value="onConversationChange"
              />
            </div>
          </template>
          先选一个角色才能挑具体对话
        </n-tooltip>
      </div>
      <div v-if="isSingleConvMode" class="filter-hint">
        单对话模式：趋势图变形为「情绪弧线」，时间段失效，分布/日历显示该对话全部数据
      </div>
    </div>

    <n-spin :show="loading">
      <div class="charts-grid">
        <div class="chart-row full-width">
          <MoodTrendChart :mode="trendMode" :data="trendData" />
        </div>
        <div class="chart-row two-col">
          <MoodPieChart :data="distributionData" />
          <MoodCalendar :data="calendarData" :month="currentMonth" />
        </div>
      </div>
    </n-spin>
  </PageShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NButtonGroup, NIcon, NSpin, NSelect, NTooltip, useMessage,
} from 'naive-ui'
import { ArrowBack } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import {
  fetchEmotionTrend, fetchEmotionDistribution, fetchEmotionCalendar,
  fetchScopePersonas, fetchScopeConversations,
} from '../api/emotion'
import MoodTrendChart from '../components/mood/MoodTrendChart.vue'
import MoodPieChart from '../components/mood/MoodPieChart.vue'
import MoodCalendar from '../components/mood/MoodCalendar.vue'
import type {
  EmotionArcPoint, EmotionCalendarItem, EmotionDistributionItem,
  EmotionScopeConversation, EmotionScopePersona, EmotionTrendPoint,
} from '../types'

const route = useRoute()
const router = useRouter()
const msg = useMessage()
const loading = ref(true)

// URL 持久化 + 本地状态
const days = ref(parseInt((route.query.days as string) || '7'))
const personaId = ref<string | null>((route.query.persona_id as string) || null)
const conversationId = ref<string | null>((route.query.conversation_id as string) || null)

const trendData = ref<EmotionTrendPoint[] | EmotionArcPoint[]>([])
const distributionData = ref<EmotionDistributionItem[]>([])
const calendarData = ref<EmotionCalendarItem[]>([])
const currentMonth = ref(new Date().toISOString().slice(0, 7))

// Filter 数据源
const loadingPersonas = ref(false)
const loadingConvs = ref(false)
const personas = ref<EmotionScopePersona[]>([])
const conversations = ref<EmotionScopeConversation[]>([])

const personaOptions = computed(() =>
  personas.value.map(p => ({ label: p.name, value: p.id }))
)
const conversationOptions = computed(() =>
  conversations.value.map(c => ({ label: c.title, value: c.id }))
)

const isSingleConvMode = computed(() => !!conversationId.value)
const trendMode = computed<'date' | 'arc'>(() => isSingleConvMode.value ? 'arc' : 'date')

function syncToUrl() {
  const q: Record<string, string> = {}
  if (days.value !== 7) q.days = String(days.value)
  if (personaId.value) q.persona_id = personaId.value
  if (conversationId.value) q.conversation_id = conversationId.value
  router.replace({ query: q })
}

async function loadData() {
  loading.value = true
  const filters = {
    persona_id: personaId.value,
    conversation_id: conversationId.value,
  }
  const results = await Promise.allSettled([
    fetchEmotionTrend(days.value, filters),
    fetchEmotionDistribution(days.value, filters),
    fetchEmotionCalendar(currentMonth.value, filters),
  ])

  const [trend, dist, cal] = results

  if (trend.status === 'fulfilled') trendData.value = trend.value
  else { console.error('情绪趋势加载失败:', trend.reason); msg.error('趋势数据加载失败') }

  if (dist.status === 'fulfilled') distributionData.value = dist.value
  else { console.error('情绪分布加载失败:', dist.reason); msg.error('分布数据加载失败') }

  if (cal.status === 'fulfilled') calendarData.value = cal.value
  else { console.error('情绪日历加载失败:', cal.reason); msg.error('日历数据加载失败') }

  loading.value = false
}

async function loadPersonas() {
  loadingPersonas.value = true
  try {
    personas.value = await fetchScopePersonas()
  } catch {
    // 无数据时 dropdown 为空，filter 不可用即可
  } finally {
    loadingPersonas.value = false
  }
}

async function loadConversations(pid: string) {
  loadingConvs.value = true
  try {
    conversations.value = await fetchScopeConversations(pid)
  } catch {
    conversations.value = []
  } finally {
    loadingConvs.value = false
  }
}

function switchDays(d: number) {
  if (isSingleConvMode.value) return
  days.value = d
  syncToUrl()
  loadData()
}

function onPersonaChange(v: string | null) {
  personaId.value = v
  // 取消 persona 时 conv 也必须清掉（级联约束）
  if (!v) {
    conversationId.value = null
    conversations.value = []
  } else {
    // 切换 persona 时清掉旧 conv 选择
    if (conversationId.value && !conversations.value.find(c => c.id === conversationId.value)) {
      conversationId.value = null
    }
    loadConversations(v)
  }
  syncToUrl()
  loadData()
}

function onConversationChange(v: string | null) {
  conversationId.value = v
  syncToUrl()
  loadData()
}

onMounted(async () => {
  await loadPersonas()
  if (personaId.value) {
    await loadConversations(personaId.value)
  }
  loadData()
})

// URL 直接带 persona_id 时需要补加载 conv 列表（已在 onMounted 处理）
watch(() => route.query, () => {
  // 用户后退/前进时同步状态（不重复 loadData，因为 routes 切换不重挂载）
}, { deep: true })
</script>

<style scoped>
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.page-title { flex: 1; margin: 0; font-size: 20px; white-space: nowrap; }
.filter-bar {
  display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
  padding: 14px 18px; background: var(--color-bg-surface, #fff); border-radius: 10px;
  margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.filter-item { display: flex; align-items: center; gap: 8px; }
.filter-label { font-size: 13px; color: var(--color-text-secondary); }
.conv-wrapper { display: inline-block; }
.filter-hint {
  font-size: 12px; color: var(--color-text-tertiary, #888);
  background: var(--color-bg-hover, #f5f5fa); padding: 4px 10px; border-radius: 6px;
}
.charts-grid { display: flex; flex-direction: column; gap: 20px; }
.chart-row.full-width { width: 100%; }
.chart-row.two-col { display: flex; gap: 20px; }
.chart-row.two-col > * { flex: 1; min-width: 0; }
</style>
