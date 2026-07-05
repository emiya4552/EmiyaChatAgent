<template>
  <!--
    ADR-0008d 卡 UI 停靠栏。右侧可折叠面板，装浏览器 MVU Host 的可见 iframe（卡的浮动面板 /
    世界书控制 / 手机终端渲染在里面）。容器 `mount` 在挂载时注册给 chat store，Host iframe 直接
    建进这个容器（**建成后不可移动**，故容器需先于 Host 存在）。用 v-show（display:none）保持
    容器常驻，卡 UI 不因显隐重载。仅当 chatStore.mvuHostActive（卡有可渲染 UI 且容器就绪）时显示。
  -->
  <div
    v-show="chatStore.mvuHostActive"
    :class="['mvu-host-dock', { collapsed }]"
  >
    <button class="mvu-dock-tab" :title="collapsed ? '展开卡界面' : '收起卡界面'" @click="collapsed = !collapsed">
      <span class="chev">{{ collapsed ? '‹' : '›' }}</span>
      <span v-if="collapsed" class="tab-label">卡界面</span>
    </button>
    <div class="mvu-dock-body">
      <div class="mvu-dock-header">
        <span class="title">卡界面</span>
        <span class="hint">MVU Host</span>
      </div>
      <!-- Host iframe 挂载点：常驻 DOM，勿用 v-if -->
      <div ref="mount" class="mvu-host-mount"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useChatStore } from '../../stores/chat'

const chatStore = useChatStore()
const mount = ref<HTMLElement | null>(null)
const collapsed = ref(false)

onMounted(() => { chatStore.registerMvuHostContainer(mount.value) })
onBeforeUnmount(() => { chatStore.registerMvuHostContainer(null) })
</script>

<style scoped>
.mvu-host-dock {
  position: absolute;
  top: 0;
  right: 0;
  height: 100%;
  width: 380px;
  max-width: 42vw;
  z-index: 20;
  display: flex;
  transition: transform 0.22s ease;
  pointer-events: none; /* 让 tab/body 各自接管，dock 空白区不挡聊天 */
}
.mvu-host-dock.collapsed {
  transform: translateX(calc(100% - 0px));
}
.mvu-dock-tab {
  position: absolute;
  left: -28px;
  top: 50%;
  transform: translateY(-50%);
  width: 28px;
  min-height: 64px;
  padding: 8px 0;
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-right: none;
  border-radius: 8px 0 0 8px;
  background: var(--n-color, #fff);
  color: var(--n-text-color, #333);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  pointer-events: auto;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.06);
}
.mvu-dock-tab .chev { font-size: 18px; line-height: 1; }
.mvu-dock-tab .tab-label { writing-mode: vertical-rl; font-size: 12px; letter-spacing: 2px; }
.mvu-dock-body {
  flex: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--n-color, #fff);
  border-left: 1px solid var(--n-border-color, #e0e0e6);
  box-shadow: -4px 0 16px rgba(0, 0, 0, 0.08);
  pointer-events: auto;
  overflow: hidden;
}
.mvu-dock-header {
  flex: 0 0 auto;
  height: 40px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--n-border-color, #e0e0e6);
  font-size: 13px;
}
.mvu-dock-header .title { font-weight: 600; }
.mvu-dock-header .hint { font-size: 11px; opacity: 0.5; }
.mvu-host-mount {
  flex: 1;
  min-height: 0;
  width: 100%;
  overflow: auto;
}
.mvu-host-mount :deep(iframe) {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
}
</style>
