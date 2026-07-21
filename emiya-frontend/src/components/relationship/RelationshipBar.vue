<template>
  <div class="relationship-stack">
    <div class="relationship-bar">
      <span v-if="mood" class="mood-summary">
        <span class="mood-emoji" aria-hidden="true">{{ moodEmoji }}</span>
        {{ mood }}<template v-if="moodIntensity != null"> · 强度 {{ moodIntensity }}/10</template>
      </span>
      <span v-if="mood" class="rel-divider" aria-hidden="true"></span>

      <template v-if="relationship">
        <strong class="relationship-title">你和 {{ personaName }}</strong>
        <n-progress
          class="rel-progress"
          type="line"
          :percentage="levelProgress"
          :height="6"
          :show-indicator="false"
          color="#a86252"
          rail-color="#eadccf"
        />
        <span class="rel-level">{{ relationship.level_name }} {{ levelProgress }}%</span>
        <span class="rel-score">· {{ scoreText }}</span>
      </template>
      <span v-else class="rel-new">这是你们的第一次对话</span>
    </div>

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
  mood?: string | null
  moodIntensity?: number | null
}

const props = defineProps<Props>()

const MOOD_EMOJI_MAP: Record<string, string> = {
  '开心': '😊', '平静': '☾', '低落': '☂', '焦虑': '◌', '愤怒': '⚡',
  '兴奋': '✦', '疲惫': '☁', '困惑': '?', '感动': '♡', '思念': '☾',
}
const moodEmoji = computed(() => MOOD_EMOJI_MAP[props.mood || ''] || '☾')

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
.relationship-stack {
  flex: none;
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-primary-bg);
}
.relationship-bar {
  display: flex;
  align-items: center;
  min-height: 34px;
  gap: 9px;
  padding: 4px 28px;
  box-sizing: border-box;
  overflow: hidden;
  font-size: 12px;
  color: var(--color-text-secondary);
  transition: all var(--transition-normal);
}
.mood-summary,
.relationship-title,
.rel-level,
.rel-score,
.rel-new {
  flex: none;
  white-space: nowrap;
}
.mood-summary {
  color: var(--color-text-tertiary);
}
.mood-emoji {
  margin-right: 3px;
  color: var(--accent-strong);
}
.rel-divider {
  width: 1px;
  height: 15px;
  flex: none;
  background: var(--color-border);
}
.relationship-title {
  color: var(--color-text);
  font-weight: 600;
}
.rel-level {
  font-weight: 600;
  color: var(--color-primary);
}
.rel-progress {
  width: 110px;
  flex: none;
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
  margin: 0 28px 6px;
  animation: fadeIn 0.3s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 720px) {
  .relationship-bar { padding-inline: 14px; }
  .rel-score { display: none; }
  .rel-progress { width: 72px; }
  .rel-alert { margin-inline: 14px; }
}
</style>
