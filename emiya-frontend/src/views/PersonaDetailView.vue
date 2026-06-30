<template>
  <PageShell maxWidth="720px">
    <div class="page-header">
      <n-button text @click="$router.back()">
        <template #icon><n-icon><ArrowBack /></n-icon></template>
        返回
      </n-button>
      <h2 class="page-title">{{ persona?.name || '加载中...' }}</h2>
      <n-button v-if="persona && !persona.is_template" size="small" @click="$router.push(`/personas/${persona.id}/edit`)">
        编辑
      </n-button>
      <n-button v-if="persona" size="small" type="info" @click="onExport">
        导出 PNG
      </n-button>
    </div>

    <n-spin :show="loading">
      <template v-if="persona">
        <!-- 基础信息 -->
        <n-card title="基础信息" class="detail-card">
          <template v-if="persona.tags?.length || persona.uses_mvu" #header-extra>
            <n-tag
              v-if="persona.uses_mvu"
              size="small"
              type="info"
              style="margin-left: 4px;"
              title="此卡使用 MVU 系统（详见 ADR-0010）"
            >MVU</n-tag>
            <n-tag v-for="t in persona.tags" :key="t" size="small" type="success" style="margin-left: 4px;">{{ t }}</n-tag>
          </template>
          <p class="info-desc"><strong>性格：</strong>{{ persona.personality }}</p>
          <p v-if="persona.background" class="info-desc"><strong>背景：</strong>{{ persona.background }}</p>
          <p v-if="persona.scenario" class="info-desc"><strong>场景：</strong>{{ persona.scenario }}</p>
          <p v-if="persona.first_message" class="info-desc"><strong>开场白：</strong>{{ persona.first_message }}</p>
          <div v-if="persona.alternate_greetings?.length" class="info-desc">
            <strong>备用开场白：</strong>
            <ul class="alt-list">
              <li v-for="(g, i) in persona.alternate_greetings" :key="i">
                <span class="alt-tag">#{{ i + 1 }}</span> {{ g }}
              </li>
            </ul>
          </div>
          <p v-if="persona.mes_example" class="info-desc"><strong>对话示例：</strong><pre class="mes-pre">{{ persona.mes_example }}</pre></p>
          <n-divider />
          <div class="info-meta">
            <span v-if="persona.source === 'imported'">来源：导入 &nbsp;·&nbsp;</span>
            <span v-if="persona.source_url">{{ persona.source_url }} &nbsp;·&nbsp;</span>
            <span>创建于 {{ new Date(persona.created_at).toLocaleDateString() }}</span>
          </div>
        </n-card>

        <!-- 关系摘要 -->
        <n-card v-if="relationship" title="你和 TA" class="detail-card relationship-card">
          <div class="rel-main">
            <span class="rel-level">{{ relationship.level_name }}</span>
            <n-progress type="line" :percentage="relationship.affinity_score" :height="8" :show-indicator="false" color="#7c5cfc" rail-color="#f0e8ff" style="flex:1; max-width: 200px;" />
            <span class="rel-score">{{ Math.round(relationship.affinity_score) }}%</span>
          </div>
          <div class="rel-meta">
            <span>认识 {{ relationship.days_span }} 天</span>
            <span>·</span>
            <span>{{ relationship.total_messages }} 轮对话</span>
            <span>·</span>
            <span>{{ relationship.deep_talk_count }} 次深度交流</span>
          </div>
          <div v-if="relationship.milestones?.length" class="rel-milestones">
            <n-tag v-for="m in relationship.milestones" :key="m" size="tiny" type="info">{{ milestoneLabels[m] || m }}</n-tag>
          </div>
        </n-card>

        <n-card v-else-if="!loading" title="你和 TA" class="detail-card">
          <p class="info-na">还没有和这个人设聊过天</p>
        </n-card>

        <!-- 卡片信息（从 card_data 只读展示；详见 docs/adr/0006） -->
        <n-card
          v-if="cardMeta.creator || cardMeta.creator_notes || cardMeta.character_version"
          title="卡片信息"
          class="detail-card card-meta-card"
        >
          <div v-if="cardMeta.creator" class="meta-row">
            <span class="meta-key">作者</span>
            <span class="meta-val">{{ cardMeta.creator }}</span>
          </div>
          <div v-if="cardMeta.character_version" class="meta-row">
            <span class="meta-key">版本</span>
            <span class="meta-val">{{ cardMeta.character_version }}</span>
          </div>
          <div v-if="cardMeta.creator_notes" class="meta-row col">
            <span class="meta-key">作者注</span>
            <pre class="meta-notes">{{ cardMeta.creator_notes }}</pre>
          </div>
        </n-card>
      </template>

      <n-empty v-if="!loading && !persona" description="角色卡不存在" />
    </n-spin>
  </PageShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NIcon, NSpin, NCard, NTag, NDivider, NProgress, NEmpty, useMessage } from 'naive-ui'
import { ArrowBack } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import { fetchPersonaDetail, exportPersonaUrl } from '../api/persona'
import { fetchRelationship } from '../api/relationship'
import type { PersonaDetail, Relationship } from '../types'

const route = useRoute()
const msg = useMessage()
const loading = ref(true)
const persona = ref<PersonaDetail | null>(null)
const relationship = ref<Relationship | null>(null)

// 从 card_data 提取只读元数据（兼容 v1 顶层 + v2/v3 data 内嵌）
const cardMeta = computed(() => {
  const card = persona.value?.card_data || {}
  const data = (card as any).data || card
  return {
    creator: (data.creator || (card as any).creator || '') as string,
    creator_notes: (data.creator_notes
      || (card as any).creator_notes
      || (card as any).creatorcomment
      || '') as string,
    character_version: (data.character_version
      || (card as any).character_version
      || '') as string,
  }
})

const milestoneLabels: Record<string, string> = {
  first_deep_talk: '第一次深度对话',
  first_vulnerability: '第一次袒露心事',
  first_joke: '第一次开玩笑',
  consecutive_days_7: '连续聊了7天',
  message_100: '100条消息',
  message_500: '500条消息',
  penetration_30: '30次深度对话',
}

onMounted(async () => {
  const pid = route.params.id as string
  try {
    const [p, r] = await Promise.all([
      fetchPersonaDetail(pid),
      fetchRelationship(pid).catch(() => null),
    ])
    persona.value = p
    relationship.value = r
  } catch {
    msg.error('加载角色卡详情失败')
  } finally {
    loading.value = false
  }
})

function onExport() {
  window.open(exportPersonaUrl(route.params.id as string), '_blank')
}
</script>

<style scoped>
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.page-title { flex: 1; margin: 0; font-size: 20px; white-space: nowrap; }
.detail-card { margin-bottom: 16px; border-radius: var(--radius-md); }
.info-desc { margin: 6px 0; line-height: 1.6; color: var(--color-text-secondary); }
.info-na { color: var(--color-text-placeholder); font-style: italic; }
.info-meta { font-size: 13px; color: var(--color-text-tertiary); }
.mes-pre {
  background: var(--color-bg-page);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 13px;
  line-height: 1.5;
  margin: 4px 0 0;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}
.relationship-card { background: linear-gradient(135deg, #faf8ff, #f5f0ff); }
.rel-main { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.rel-level { font-size: 18px; font-weight: 600; color: #7c5cfc; }
.rel-score { font-size: 14px; color: #7c5cfc; font-weight: 600; }
.rel-meta { display: flex; gap: 8px; font-size: 13px; color: #888; margin-bottom: 8px; }
.rel-milestones { display: flex; flex-wrap: wrap; gap: 4px; }

.alt-list { margin: 4px 0 0; padding-left: 20px; }
.alt-list li { margin: 4px 0; line-height: 1.5; color: var(--color-text-secondary); }
.alt-tag { color: #aaa; font-size: 12px; margin-right: 4px; }

.card-meta-card { background: var(--color-bg-surface-elevated, #fafafa); }
.meta-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  font-size: 13px;
  padding: 4px 0;
}
.meta-row.col { flex-direction: column; align-items: stretch; gap: 4px; }
.meta-key {
  color: var(--color-text-tertiary, #888);
  min-width: 4em;
}
.meta-val { color: var(--color-text-secondary); }
.meta-notes {
  background: var(--color-bg-page);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.5;
  margin: 0;
  white-space: pre-wrap;
  max-height: 240px;
  overflow-y: auto;
}
</style>
