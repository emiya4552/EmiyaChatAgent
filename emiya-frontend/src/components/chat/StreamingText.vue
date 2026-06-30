<template>
  <div class="streaming-text" :data-streaming="isStreaming || undefined">
    <div ref="bodyRef" class="markdown-body" v-html="renderedHtml"></div>
    <span v-if="isStreaming" class="cursor-blink">|</span>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { renderMarkdown } from '../../utils/markdown'
import {
  mountHtmlIframes, isHtmlIframeRenderEnabled,
} from '../../composables/useHtmlIframeRender'

const props = defineProps<{
  text: string
  isStreaming: boolean
}>()

// rAF 节流：流式期间多 token 内的渲染更新合并到一帧
// 详见 ADR-0008 Q8b=B
const renderedHtml = ref<string>('')
const bodyRef = ref<HTMLElement | null>(null)
let rafHandle: number | null = null
let pendingText: string | null = null

// 流式期不 mount iframe（避免半截 HTML 反复 reparse）；非流式 / 流式结束后 mount
function _maybeMountIframes() {
  if (props.isStreaming) return
  if (!isHtmlIframeRenderEnabled()) return
  mountHtmlIframes(bodyRef.value)
}

// 兜底：每次 renderedHtml 变化后由 Vue 在 DOM 更新后调（flush:post）
// 涵盖：开场白首次渲染、fetchMessages 历史填充、流式结束、用户切换对话等
watch(renderedHtml, () => {
  _maybeMountIframes()
}, { flush: 'post' })

function _flush(): void {
  rafHandle = null
  if (pendingText === null) return
  renderedHtml.value = renderMarkdown(pendingText)
  pendingText = null
}

function _schedule(text: string): void {
  pendingText = text
  if (rafHandle !== null) return
  if (typeof requestAnimationFrame === 'function') {
    rafHandle = requestAnimationFrame(_flush)
  } else {
    _flush()
  }
}

watch(
  () => props.text,
  (newText) => {
    if (props.isStreaming) {
      _schedule(newText)
    } else {
      // 非流式：同步渲染（避免拼写过程的视觉割裂）
      if (rafHandle !== null) {
        cancelAnimationFrame(rafHandle)
        rafHandle = null
      }
      pendingText = null
      renderedHtml.value = renderMarkdown(newText)
      _maybeMountIframes()
    }
  },
  { immediate: true },
)

// 流式结束时强制刷新一次，保证最终态准确
watch(
  () => props.isStreaming,
  (streaming) => {
    if (!streaming) {
      if (rafHandle !== null) {
        cancelAnimationFrame(rafHandle)
        rafHandle = null
      }
      renderedHtml.value = renderMarkdown(props.text)
      pendingText = null
      // 流式结束：触发一次 iframe mount
      _maybeMountIframes()
    }
  },
)

// 首次挂载时再 mount 一次 —— 修复"开场白 / 历史消息 fetch 出来后没渲染 iframe"
// 的 race：immediate watcher 在 setup 阶段同步触发，那时 bodyRef 还是 null，
// 即便 nextTick 也只能保证 DOM 挂好，组件实例可能尚未走完 mount 链。
onMounted(() => {
  _maybeMountIframes()
})

onUnmounted(() => {
  if (rafHandle !== null) {
    cancelAnimationFrame(rafHandle)
  }
})
</script>

<style scoped>
.streaming-text {
  word-break: break-word;
}
.markdown-body {
  word-break: break-word;
}

/* 流式期间 <details> 强制展开 + summary 禁点击：避免折叠面板半开闪烁
   详见 ADR-0008 Q4=B+ */
.streaming-text[data-streaming] :deep(details) {
  display: block;
}
.streaming-text[data-streaming] :deep(details > *:not(summary)) {
  display: revert;
}
.streaming-text[data-streaming] :deep(summary) {
  pointer-events: none;
  list-style: none;
}
.streaming-text[data-streaming] :deep(summary::-webkit-details-marker) {
  display: none;
}

.markdown-body :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 8px;
  padding: 12px 16px;
  overflow-x: auto;
  line-height: 1.6;
}
.markdown-body :deep(pre) code {
  font-family: 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 14px;
  color: inherit;
  background: none;
  padding: 0;
}
.markdown-body :deep(:not(pre) > code) {
  font-family: 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px;
  background: rgba(99, 102, 241, 0.12);
  color: #6366f1;
  padding: 2px 6px;
  border-radius: 4px;
}
.markdown-body :deep(p) {
  margin: 4px 0;
}
.markdown-body :deep(details) {
  margin: 8px 0;
}
.markdown-body :deep(summary) {
  cursor: pointer;
}
.cursor-blink {
  animation: blink 1s step-end infinite;
  font-weight: bold;
}
@keyframes blink {
  50% { opacity: 0; }
}
</style>
