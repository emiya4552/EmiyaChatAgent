<template>
  <div class="chart-wrapper">
    <h4 class="chart-title">情绪日历 {{ month }}</h4>
    <v-chart v-if="data.length" :option="option" autoresize style="height: 350px" />
    <n-empty v-else description="暂无数据" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { HeatmapChart } from 'echarts/charts'
import { TooltipComponent, GridComponent, VisualMapComponent, CalendarComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { NEmpty } from 'naive-ui'
import type { EmotionCalendarItem } from '../../types'

use([HeatmapChart, TooltipComponent, GridComponent, VisualMapComponent, CalendarComponent, CanvasRenderer])

const props = defineProps<{ data: EmotionCalendarItem[]; month: string }>()

const COLORS: Record<string, string> = {
  '开心': '#52c41a', '兴奋': '#faad14', '感动': '#eb2f96',
  '平静': '#1890ff', '困惑': '#722ed1', '焦虑': '#fa8c16',
  '思念': '#69c0ff', '低落': '#8c8c8c', '疲惫': '#a0a0a0', '愤怒': '#f5222d',
}

const option = computed(() => {
  const range = [props.month + '-01', props.month + '-31']
  const chartData = props.data
    .filter(d => d.dominant_emotion)
    .map(d => [d.date, d.avg_intensity ?? 0])

  return {
    tooltip: {
      formatter: (params: any) => {
        const item = props.data.find(d => d.date === params.value[0])
        if (item) return `${item.date}<br/>${item.dominant_emotion} · 强度 ${item.avg_intensity}/10`
        return params.value[0]
      },
    },
    visualMap: {
      min: 0, max: 10,
      orient: 'horizontal' as const,
      left: 'center',
      bottom: 5,
      inRange: { color: ['#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#216e39'] },
    },
    calendar: {
      range,
      dayLabel: { nameMap: 'ZH' },
      monthLabel: { nameMap: 'ZH' },
      cellSize: ['auto', 32],
      top: 40,
    },
    series: [{
      type: 'heatmap',
      coordinateSystem: 'calendar',
      data: chartData,
    }],
  }
})
</script>

<style scoped>
.chart-wrapper { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.chart-title { margin: 0 0 12px; font-size: 16px; }
</style>
