<template>
  <div v-if="relationship" class="relationship-bar">
    <span class="rel-level">{{ relationship.level_name }}</span>
    <span class="rel-sep">·</span>
    <span>已聊 {{ relationship.total_messages }} 条消息</span>
    <n-progress
      class="rel-progress"
      type="line"
      :percentage="levelProgress"
      :height="6"
      :show-indicator="false"
      color="#7c5cfc"
      rail-color="#e8e0ff"
    />
    <span class="rel-score">{{ scoreText }}</span>

    <!-- 好感度变动提示 -->
    <n-alert
      v-if="showAffinityDelta"
      class="rel-alert"
      :type="affinityDelta > 0 ? 'success' : 'warning'"
      :bordered="false"
    >
      {{ affinityReason }}
    </n-alert>

    <!-- 等级变化提示 -->
    <n-alert
      v-if="showLevelUp"
      class="rel-alert"
      type="success"
      :bordered="false"
    >
      🎉 你们的关系升级了！
    </n-alert>

    <!-- 里程碑提示 -->
    <n-alert
      v-if="showMilestone"
      class="rel-alert"
      type="info"
      :bordered="false"
    >
      {{ milestoneMsg }}
    </n-alert>
  </div>
  <div v-else class="relationship-bar empty">
    <span class="rel-new">这是你们的第一次对话</span>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { NProgress, NAlert } from 'naive-ui'
import type { Relationship } from '../../types'

/** 好感度等级阈值 */
const LEVEL_THRESHOLDS = [
  { level: 0, name: '陌生人', min: 0, max: 15 },
  { level: 1, name: '熟人', min: 15, max: 35 },
  { level: 2, name: '朋友', min: 35, max: 60 },
  { level: 3, name: '密友', min: 60, max: 85 },
  { level: 4, name: '知己', min: 85, max: 100 },
]

/** 当前等级内的进度百分比（而非全局%） */
function calcLevelProgress(affinity: number, level: number): number {
  const t = LEVEL_THRESHOLDS.find((l) => l.level === level)
  if (!t || t.max <= t.min) return 0
  const pct = ((affinity - t.min) / (t.max - t.min)) * 100
  return Math.max(0, Math.min(100, Math.round(pct)))
}

interface Props {
  relationship: Relationship | null
  personaName: string
}

const props = defineProps<Props>()

const showLevelUp = ref(false)
const showMilestone = ref(false)
const milestoneMsg = ref('')
const showAffinityDelta = ref(false)
const affinityReason = ref('')
const affinityDelta = ref(0)
const _lastAffinity = ref<number | null>(null)

/** 等级内进度百分比 */
const levelProgress = computed(() => {
  if (!props.relationship) return 0
  // 新关系（消息 < 10 且分数为 0）：进度从 1% 起步
  if (props.relationship.total_messages < 10 && props.relationship.affinity_score < 1) return 1
  return calcLevelProgress(props.relationship.affinity_score, props.relationship.level)
})

/** 距离下一级还有多少分 */
const scoreText = computed(() => {
  if (!props.relationship) return ''
  const t = LEVEL_THRESHOLDS.find((l) => l.level === props.relationship!.level)
  if (!t) return `${Math.round(props.relationship.affinity_score)} 分`
  const remaining = Math.max(0, t.max - props.relationship.affinity_score)
  if (remaining <= 0) return '已满级'
  return `${Math.round(props.relationship.affinity_score)} 分 · 距「${LEVEL_THRESHOLDS[Math.min(props.relationship.level + 1, 4)]?.name || '下一级'}」${Math.round(remaining)} 分`
})

/** 外部调用：显示好感度变动提示 */
function showAffinityChange(delta: number, reason: string) {
  affinityDelta.value = delta
  affinityReason.value = reason
  showAffinityDelta.value = true
  setTimeout(() => { showAffinityDelta.value = false }, 5000)
}

watch(() => props.relationship, (rel) => {
  if (!rel) return
  // 检测好感度变化
  if (_lastAffinity.value !== null && _lastAffinity.value !== rel.affinity_score) {
    const delta = rel.affinity_score - _lastAffinity.value
    if (delta !== 0) {
      affinityDelta.value = delta
      affinityReason.value = delta > 0
        ? `好感度 +${Math.round(delta)}（${rel.level_name}）`
        : `好感度 ${Math.round(delta)}`
      showAffinityDelta.value = true
      setTimeout(() => { showAffinityDelta.value = false }, 4000)
    }
  }
  _lastAffinity.value = rel.affinity_score

  if (rel.level_changed) {
    showLevelUp.value = true
    setTimeout(() => { showLevelUp.value = false }, 4000)
  }
  if (rel.new_milestone) {
    const map: Record<string, string> = {
      first_deep_talk: '第一次深度对话 — 你们更了解彼此了',
      message_100: '已经聊了 100 条消息了！',
      message_500: '500 条消息 — 这段关系很特别',
      consecutive_days_7: '连续聊了 7 天 — 习惯彼此的存在',
      penetration_30: '深度对话达 30 次 — 知心好友',
    }
    milestoneMsg.value = map[rel.new_milestone] || rel.new_milestone
    showMilestone.value = true
    setTimeout(() => { showMilestone.value = false }, 5000)
  }
})

defineExpose({ showAffinityChange })
</script>

<style scoped>
.relationship-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: var(--color-primary-bg);
  border-bottom: 1px solid var(--color-border-light);
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--color-text-secondary);
  transition: all var(--transition-normal);
}
.relationship-bar.empty {
  color: var(--color-text-tertiary);
}
.rel-level {
  font-weight: 600;
  color: var(--color-primary);
}
.rel-sep {
  color: var(--color-border);
}
.rel-progress {
  flex: 1;
  max-width: 120px;
  min-width: 60px;
}
.rel-score {
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.rel-new {
  font-style: italic;
}
.rel-alert {
  width: 100%;
  margin-top: 4px;
  animation: fadeIn 0.3s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
