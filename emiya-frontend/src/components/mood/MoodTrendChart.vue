<template>
  <div class="chart-wrapper">
    <h4 class="chart-title">{{ mode === 'arc' ? '情绪弧线（按消息序）' : '情绪趋势（按日期）' }}</h4>
    <v-chart v-if="hasData" :option="option" autoresize style="height: 320px" />
    <n-empty v-else description="暂无情绪数据" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { NEmpty } from 'naive-ui'
import type { EmotionArcPoint, EmotionTrendPoint } from '../../types'

use([LineChart, TitleComponent, TooltipComponent, GridComponent, CanvasRenderer])

const props = defineProps<{
  // 'date' = 多对话模式（按日期聚合）；'arc' = 单对话模式（按消息序）
  mode: 'date' | 'arc'
  data: EmotionTrendPoint[] | EmotionArcPoint[]
}>()

const EMOTION_EMOJI: Record<string, string> = {
  '开心': '😊', '平静': '😌', '低落': '😔', '焦虑': '😰', '愤怒': '😤',
  '兴奋': '🤩', '疲惫': '😴', '困惑': '🤔', '感动': '🥹', '思念': '💭',
}

const hasData = computed(() => props.data.length > 0)

const option = computed(() => {
  if (props.mode === 'arc') {
    const arc = props.data as EmotionArcPoint[]
    return {
      tooltip: {
        trigger: 'item' as const,
        formatter: (params: any) => {
          const p: EmotionArcPoint = params.data._raw
          const trig = p.triggers.length ? `<br/>触发: ${p.triggers.join(', ')}` : ''
          const tm = p.created_at ? `<br/><small>${new Date(p.created_at).toLocaleString()}</small>` : ''
          return `#${p.idx} ${EMOTION_EMOJI[p.emotion] || ''} ${p.emotion} · 强度 ${p.intensity}/10${trig}${tm}`
        },
      },
      grid: { left: 40, right: 20, top: 20, bottom: 40 },
      xAxis: {
        type: 'category' as const,
        name: '消息序号',
        data: arc.map(d => `#${d.idx}`),
      },
      yAxis: { type: 'value' as const, min: 0, max: 10, name: '强度' },
      series: [{
        type: 'line',
        data: arc.map(d => ({
          value: d.intensity,
          label: EMOTION_EMOJI[d.emotion] || '',
          _raw: d,
        })),
        smooth: true,
        symbolSize: 10,
        lineStyle: { color: '#667eea' },
        itemStyle: { color: '#667eea' },
        label: { show: arc.length <= 30, position: 'top', fontSize: 16, formatter: (p: any) => p.data.label },
        areaStyle: { color: 'rgba(168, 98, 82, 0.1)' },
      }],
    }
  }

  // mode === 'date'
  const trend = props.data as EmotionTrendPoint[]
  return {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category' as const,
      data: trend.map(d => d.date.slice(5)),
    },
    yAxis: { type: 'value' as const, min: 0, max: 10 },
    series: [{
      type: 'line',
      data: trend.map(d => ({
        value: d.avg_intensity,
        label: d.dominant_emotion ? EMOTION_EMOJI[d.dominant_emotion] || '' : '',
      })),
      smooth: true,
      lineStyle: { color: '#a86252' },
      itemStyle: { color: '#a86252' },
      label: { show: trend.length <= 10, position: 'top', fontSize: 16 },
      areaStyle: { color: 'rgba(168, 98, 82, 0.1)' },
    }],
  }
})
</script>

<style scoped>
.chart-wrapper { background: var(--color-bg-surface); border-radius: 10px; padding: 20px; box-shadow: var(--shadow-sm); }
.chart-title { margin: 0 0 12px; font-size: 16px; }
</style>
