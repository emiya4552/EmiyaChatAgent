<template>
  <!--
    ADR-0008d 卡 UI —— **覆盖式布局**（贴近 ST）。浏览器 MVU Host 的可见 iframe 铺满聊天区、
    透明背景，卡的 position:fixed 浮层（悬浮球 / 世界书控制 / 飞讯手机终端）就能像在 ST 整窗里
    一样铺开、随意拖曳。

    穿透编排：iframe 默认 pointer-events:none（空白处点击/打字穿透给底下的聊天）。Host 上报卡 UI
    元素的矩形；本组件用 document pointermove（pe:none 时）+ Host 回传的指针（pe:auto 时）做命中
    检测，鼠标落到卡 UI 上才把 iframe 切成可点。容器 mount 常驻（v-show，不 v-if），iframe 建成后
    不重载。
  -->
  <div v-show="chatStore.mvuHostActive" class="mvu-host-root">
    <div v-show="chatUi.cardUiVisible" ref="overlay" class="mvu-host-overlay">
      <!-- Host iframe 挂载点：常驻 DOM，勿用 v-if -->
      <div ref="mount" class="mvu-host-mount"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useChatStore } from '../../stores/chat'
import { useChatUiStore } from '../../stores/chatUi'

const chatStore = useChatStore()
const chatUi = useChatUiStore()
const overlay = ref<HTMLElement | null>(null)
const mount = ref<HTMLElement | null>(null)

type Rect = { x: number; y: number; w: number; h: number }
let rects: Rect[] = [] // Host 上报的卡 UI 矩形（iframe 视口坐标）

function iframeEl(): HTMLIFrameElement | null {
  return (mount.value?.querySelector('iframe') as HTMLIFrameElement) || null
}
function hit(ix: number, iy: number): boolean {
  return rects.some((r) => ix >= r.x && ix <= r.x + r.w && iy >= r.y && iy <= r.y + r.h)
}
function setPe(over: boolean) {
  const f = iframeEl()
  if (f) f.style.pointerEvents = chatUi.cardUiVisible && over ? 'auto' : 'none'
}
// Host → 父：卡 UI 矩形 + pe:auto 时的指针位置（父窗口据此判断何时切回穿透）。
function onWinMsg(ev: MessageEvent) {
  const d: any = ev.data
  if (!d || d.__mvu == null) return
  if (d.type === 'ui-rects') rects = Array.isArray(d.rects) ? d.rects : []
  else if (d.type === 'host-pointer') setPe(hit(d.x, d.y)) // 已是 iframe 坐标
}
// pe:none 时鼠标事件走父窗口 document：换算成 iframe 坐标做命中，命中就切 pe:auto。
function onDocMove(e: PointerEvent) {
  if (!chatUi.cardUiVisible || !chatStore.mvuHostActive) return
  const ov = overlay.value?.getBoundingClientRect()
  if (!ov) return
  setPe(hit(e.clientX - ov.left, e.clientY - ov.top))
}

onMounted(() => {
  chatStore.registerMvuHostContainer(mount.value)
  window.addEventListener('message', onWinMsg)
  document.addEventListener('pointermove', onDocMove, true)
})
onBeforeUnmount(() => {
  chatStore.registerMvuHostContainer(null)
  window.removeEventListener('message', onWinMsg)
  document.removeEventListener('pointermove', onDocMove, true)
})
</script>

<style scoped>
/* 覆盖聊天区（ChatMain 相对容器内 inset:0），默认穿透，不挡聊天。 */
.mvu-host-root {
  position: absolute;
  inset: 0;
  z-index: 20;
  pointer-events: none;
}
.mvu-host-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none; /* iframe 自身 pe 由脚本按命中切换 */
}
.mvu-host-mount {
  position: absolute;
  inset: 0;
}
.mvu-host-mount :deep(iframe) {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
  background: transparent;
}
</style>
