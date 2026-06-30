<template>
  <div class="chart-wrapper">
    <h4 class="chart-title">情绪分布</h4>
    <v-chart v-if="data.length" :option="option" autoresize style="height: 320px" />
    <n-empty v-else description="暂无数据" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { NEmpty } from 'naive-ui'
import type { EmotionDistributionItem } from '../../types'

use([PieChart, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{ data: EmotionDistributionItem[] }>()

const COLORS: Record<string, string> = {
  '开心': '#52c41a', '兴奋': '#faad14', '感动': '#eb2f96',
  '平静': '#1890ff', '困惑': '#722ed1', '焦虑': '#fa8c16',
  '思念': '#69c0ff', '低落': '#8c8c8c', '疲惫': '#a0a0a0', '愤怒': '#f5222d',
}

const option = computed(() => ({
  tooltip: { trigger: 'item' as const, formatter: '{b}: {c}次 ({d}%)' },
  legend: { orient: 'vertical', right: 5, top: 'center', itemGap: 8, textStyle: { fontSize: 12 } },
  series: [{
    type: 'pie',
    center: ['35%', '50%'],
    radius: ['35%', '65%'],
    itemStyle: {
      color: (params: any) => COLORS[params.name] || '#ccc',
    },
    label: { formatter: '{b}\n{d}%' },
    data: props.data.map(d => ({ name: d.emotion, value: d.count })),
  }],
}))
</script>

<style scoped>
.chart-wrapper { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.chart-title { margin: 0 0 12px; font-size: 16px; }
</style>
