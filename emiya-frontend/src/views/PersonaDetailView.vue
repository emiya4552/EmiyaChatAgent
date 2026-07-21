<template>
  <PageShell maxWidth="720px">
    <WorkspaceHeader
      eyebrow="角色卡"
      :title="persona?.name || '加载中...'"
      backTo="/personas"
      backLabel="所有角色"
    >
      <template #actions>
        <n-button v-if="persona && !persona.is_template" @click="$router.push(`/personas/${persona.id}/edit`)">
          编辑
        </n-button>
        <n-button v-if="persona" type="primary" @click="onExport">
          导出 PNG
        </n-button>
      </template>
    </WorkspaceHeader>

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

        <n-card v-if="mvuReport?.is_mvu_card" title="MVU 兼容性" class="detail-card mvu-card">
          <div class="mvu-head">
            <n-tag size="small" :type="mvuReport.level === 'partial' ? 'warning' : 'success'">
              {{ mvuReport.level === 'partial' ? '部分兼容' : '已兼容' }}
            </n-tag>
            <span class="mvu-summary">
              {{ mvuReport.supported.length }} 项已支持，{{ mvuReport.unsupported.length }} 项需降级
            </span>
          </div>

          <n-collapse arrow-placement="right" class="mvu-collapse">
            <n-collapse-item :title="`已兼容 (${supportedDetails.length})`" name="supported">
              <div v-if="supportedDetails.length" class="mvu-detail-list">
                <div v-for="item in supportedDetails" :key="item.code" class="mvu-detail supported">
                  <div class="mvu-detail-head">
                    <n-tag size="small" type="success">兼容</n-tag>
                    <strong>{{ item.title }}</strong>
                    <span v-if="item.count" class="mvu-count">{{ item.count }}</span>
                  </div>
                  <p class="mvu-detail-summary">{{ item.summary }}</p>
                  <p class="mvu-detail-body">{{ item.detail }}</p>
                  <div v-if="item.evidence?.length" class="mvu-evidence">
                    <span v-for="e in item.evidence.slice(0, 8)" :key="`${item.code}-${e}`">{{ e }}</span>
                  </div>
                </div>
              </div>
              <p v-else class="mvu-empty">暂未检测到明确兼容项</p>
            </n-collapse-item>

            <n-collapse-item :title="`未兼容 / 降级 (${unsupportedDetails.length})`" name="unsupported">
              <div v-if="unsupportedDetails.length" class="mvu-detail-list">
                <div v-for="item in unsupportedDetails" :key="item.code" class="mvu-detail unsupported">
                  <div class="mvu-detail-head">
                    <n-tag size="small" type="warning">降级</n-tag>
                    <strong>{{ item.title }}</strong>
                    <span v-if="item.count" class="mvu-count">{{ item.count }}</span>
                  </div>
                  <p class="mvu-detail-summary">{{ item.summary }}</p>
                  <p class="mvu-detail-body">{{ item.detail }}</p>
                  <div v-if="item.evidence?.length" class="mvu-evidence">
                    <span v-for="e in item.evidence.slice(0, 8)" :key="`${item.code}-${e}`">{{ e }}</span>
                  </div>
                </div>
              </div>
              <p v-else class="mvu-empty">没有发现需要降级处理的能力</p>
            </n-collapse-item>

            <n-collapse-item :title="`检测特征 (${mvuFeatureEntries.length})`" name="features">
              <div class="mvu-feature-grid">
                <div v-for="[key, value] in mvuFeatureEntries" :key="key" class="mvu-feature">
                  <span class="mvu-feature-key">{{ featureLabel(key) }}</span>
                  <span class="mvu-feature-val">{{ value }}</span>
                </div>
              </div>
              <div v-if="mvuReport.warnings.length" class="mvu-warnings">
                <p v-for="w in mvuReport.warnings.slice(0, 6)" :key="w">{{ w }}</p>
              </div>
            </n-collapse-item>
          </n-collapse>
        </n-card>

        <!-- 关系摘要 -->
        <n-card v-if="relationship" title="你和 TA" class="detail-card relationship-card">
          <div class="rel-main">
            <span class="rel-level">{{ relationship.level_name }}</span>
            <n-progress type="line" :percentage="relationship.affinity_score" :height="8" :show-indicator="false" color="var(--color-primary)" rail-color="var(--accent-soft)" style="flex:1; max-width: 200px;" />
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
import {
  NButton, NIcon, NSpin, NCard, NTag, NDivider, NProgress, NEmpty,
  NCollapse, NCollapseItem, useMessage,
} from 'naive-ui'
import { ArrowBack } from '@vicons/ionicons5'
import PageShell from '../components/layout/PageShell.vue'
import WorkspaceHeader from '../components/layout/WorkspaceHeader.vue'
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

const mvuReport = computed(() => persona.value?.mvu_compatibility || null)
const mvuFeatureEntries = computed(() => {
  const features = mvuReport.value?.features || {}
  return Object.entries(features).filter(([, value]) => Number(value) > 0)
})
const mvuDetails = computed(() => mvuReport.value?.details || [])
const supportedDetails = computed(() =>
  mvuDetails.value.filter(item => item.status === 'supported')
)
const unsupportedDetails = computed(() =>
  mvuDetails.value.filter(item => item.status === 'unsupported')
)

function featureLabel(key: string): string {
  const labels: Record<string, string> = {
    initvar_entries: '[initvar] 条目',
    opening_entries: '[opening] 条目',
    tavern_helper_scripts: '助手脚本',
    remote_scripts: '远程脚本',
    regex_scripts: '正则脚本',
    html_fragments: 'HTML 片段',
    schema_defaults: 'Schema 默认值',
  }
  return labels[key] || key
}

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
.detail-card { margin-bottom: 16px; border-radius: var(--radius-md); background: var(--color-bg-surface); }
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
.relationship-card { background: color-mix(in srgb, var(--accent) 8%, var(--color-bg-surface)); }
.rel-main { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.rel-level { font-size: 18px; font-weight: 600; color: var(--color-primary); }
.rel-score { font-size: 14px; color: var(--color-primary); font-weight: 600; }
.rel-meta { display: flex; gap: 8px; font-size: 13px; color: var(--color-text-secondary); margin-bottom: 8px; }
.rel-milestones { display: flex; flex-wrap: wrap; gap: 4px; }

.alt-list { margin: 4px 0 0; padding-left: 20px; }
.alt-list li { margin: 4px 0; line-height: 1.5; color: var(--color-text-secondary); }
.alt-tag { color: var(--color-text-tertiary); font-size: 12px; margin-right: 4px; }

.card-meta-card { background: var(--color-bg-surface-elevated, #fafafa); }
.mvu-card { background: var(--color-bg-elevated); }
.mvu-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.mvu-summary { font-size: 13px; color: var(--color-text-secondary); }
.mvu-collapse { margin-top: 4px; }
.mvu-detail-list { display: flex; flex-direction: column; gap: 10px; }
.mvu-detail {
  border: 1px solid var(--color-border, #eee);
  border-radius: 6px;
  padding: 10px 12px;
  background: var(--color-bg-surface, #fff);
}
.mvu-detail.supported { border-left: 3px solid #18a058; }
.mvu-detail.unsupported { border-left: 3px solid #f0a020; }
.mvu-detail-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.mvu-count {
  margin-left: auto;
  min-width: 22px;
  text-align: right;
  color: var(--color-text-tertiary);
  font-weight: 600;
}
.mvu-detail-summary {
  margin: 8px 0 0;
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}
.mvu-detail-body {
  margin: 6px 0 0;
  color: var(--color-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}
.mvu-evidence {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.mvu-evidence span {
  max-width: 100%;
  border: 1px solid var(--color-border, #eee);
  border-radius: 999px;
  padding: 2px 8px;
  color: var(--color-text-secondary);
  background: var(--color-bg-page, #f7f7f7);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mvu-empty {
  margin: 0;
  color: var(--color-text-tertiary);
  font-size: 13px;
}
.mvu-feature-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.mvu-feature {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid var(--color-border, #eee);
  border-radius: 6px;
  background: var(--color-bg-surface, #fff);
  font-size: 12px;
}
.mvu-feature-key { color: var(--color-text-tertiary); }
.mvu-feature-val { font-weight: 600; color: var(--color-text-secondary); }
.mvu-warnings {
  margin-top: 10px;
  color: var(--color-danger);
  font-size: 12px;
  line-height: 1.5;
}
.mvu-warnings p { margin: 4px 0; }
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
