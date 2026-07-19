<!--
  PROTOTYPE — full-surface UI exploration. Read-only, local state only.
  Three structural variants are available at ?variant=A|B|C.
-->
<template>
  <main class="prototype" :class="[`scope-${scope}`, `variant-${variant.toLowerCase()}`]">
    <!-- A: a persistent studio desk -->
    <section v-if="variant === 'A'" class="desk">
      <section class="desk-content">
        <header class="desk-header"><div><p>{{ config.kicker }}</p><h1>{{ activeSurface.name }}</h1></div><button class="accent" @click="advanceState">{{ activeSurface.action }}　→</button></header>
        <SurfaceDetail :surface="activeSurface" :records="records" mode="desk" @inspect="inspect" />
        <MockVisualData :scope="scope" :surface-id="activeSurface.id" />
      </section>
      <aside class="desk-context"><p class="eyebrow">本工作面覆盖</p><h2>{{ activeSurface.coverage.length }} 个正式能力</h2><ul><li v-for="line in activeSurface.coverage" :key="line">{{ line }}</li></ul><div class="signal"><span>●</span> 所有操作均为展示状态<br><small>不调用后端，也不写入数据</small></div></aside>
    </section>

    <!-- B: a flow-first board; no persistent navigation -->
    <section v-else-if="variant === 'B'" class="flow">
      <header class="flow-header"><div class="brand">EMIYA<span>✦</span></div><div class="flow-tabs"><button v-for="item in config.surfaces" :key="item.id" :class="{ active: active === item.id }" @click="active = item.id">{{ item.short }}</button></div><span>评审模式</span></header>
      <div class="flow-intro"><p>{{ config.kicker }} / 流程视角</p><h1>{{ activeSurface.question }}</h1><button class="accent" @click="advanceState">{{ activeSurface.action }}</button></div>
      <div class="flow-board">
        <article class="flow-card discover"><b>01　看见</b><h2>{{ activeSurface.name }}</h2><p>{{ activeSurface.summary }}</p><div class="metric">{{ activeSurface.metric }}</div></article>
        <article class="flow-card shape"><b>02　组织</b><div class="chip-row"><span v-for="tag in activeSurface.tags" :key="tag">{{ tag }}</span></div><h2>先决定结构，再进入细节</h2><ul><li v-for="line in activeSurface.coverage.slice(0, 3)" :key="line">{{ line }}</li></ul></article>
        <article class="flow-card act"><b>03　执行</b><SurfaceDetail :surface="activeSurface" :records="records" mode="flow" @inspect="inspect" /><MockVisualData :scope="scope" :surface-id="activeSurface.id" /><button class="accent wide" @click="advanceState">{{ activeSurface.action }}　→</button></article>
      </div>
    </section>

    <!-- C: a calm document/canvas layout -->
    <section v-else class="canvas">
      <header class="canvas-header"><div class="brand">EMIYA<span>✦</span></div><nav><button v-for="item in config.surfaces" :key="item.id" :class="{ active: active === item.id }" @click="active = item.id">{{ item.short }}</button></nav><button class="profile">我</button></header>
      <div class="canvas-grid"><aside class="canvas-index"><p>INDEX / {{ String(config.surfaces.indexOf(activeSurface) + 1).padStart(2, '0') }}</p><button v-for="item in config.surfaces" :key="item.id" @click="active = item.id">{{ item.icon }}　{{ item.name }}</button></aside><article class="canvas-main"><p class="eyebrow">{{ config.kicker }} · 方案 C</p><h1>{{ activeSurface.name }}</h1><p class="lead">{{ activeSurface.summary }}</p><SurfaceDetail :surface="activeSurface" :records="records" mode="canvas" @inspect="inspect" /><MockVisualData :scope="scope" :surface-id="activeSurface.id" /><button class="text-action" @click="advanceState">{{ activeSurface.action }} →</button></article><aside class="canvas-notes"><span>设计判断</span><h2>{{ activeSurface.question }}</h2><p>把高频操作留在当前画面，把低频配置折叠到恰好需要它的时刻。</p><hr><b>对应路由</b><code>{{ activeSurface.route }}</code><b>已覆盖</b><small v-for="line in activeSurface.coverage" :key="line">{{ line }}</small></aside></div>
    </section>

    <div class="simulation-state">模拟状态 · {{ simulationState }}</div>
    <PrototypeSwitcher :current="variant" :labels="labels" @change="setVariant" />
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import PrototypeSwitcher from './PrototypeSwitcher.vue'
import MockVisualData from './MockVisualData.vue'

type Variant = 'A' | 'B' | 'C'
type Surface = { id: string; icon: string; short: string; name: string; route: string; action: string; question: string; summary: string; metric: string; tags: string[]; coverage: string[]; fields: string[] }
type Fixture = { title: string; meta: string; value: string; tone: 'warm' | 'cool' | 'plain' }
const props = defineProps<{ scope: 'conversation' | 'studio' | 'insights' | 'account'; initialSurface?: string }>()

const scopes: Record<typeof props.scope, { kicker: string; surfaces: Surface[] }> = {
  conversation: { kicker: '对话工作区', surfaces: [
    { id: 'talk', icon: '◌', short: '对话', name: '正在进行的章节', route: '/chat', action: '继续书写', question: '怎样把沉浸式对话与即时控制放在一起？', summary: '消息是画布；角色关系、情绪和生成状态只在需要时浮现。', metric: '01 · 活跃对话', tags: ['流式回复', '开场白切换', '短 / 中 / 长'], coverage: ['会话列表、重命名、删除与当前会话切换', 'Markdown / 代码块 / 输出契约结果与诊断', '情绪、关系里程碑、生成与严格结构阶段'], fields: ['伊澜 · 月光落在旧书页上', '“也许今晚不必急着道别。”', '输入消息…　⌘ Enter 发送'] },
    { id: 'start', icon: '+', short: '新建', name: '为一段对话配置起点', route: '/chat → 新建对话', action: '开始对话', question: '如何让复杂的上下文选择仍像一次自然的开场？', summary: '角色是唯一必填项，其余上下文按“继承—覆写”逐层展开。', metric: '07 · 可选上下文', tags: ['AI 角色', '用户角色', '世界书'], coverage: ['AI / 用户角色、标题和开场白选择', '预设、模板、世界书（多选）与正则预设', '角色默认携带内容的预填与可见来源'], fields: ['AI 角色　伊澜', '世界书　旧城档案 · 港口传闻', 'Prompt 模板　叙事长篇'] },
    { id: 'control', icon: '≡', short: '控制', name: '本次对话的控制台', route: '/chat → 对话设置', action: '保存覆盖', question: '怎样让“强大配置”不打断故事？', summary: '按使用时机分组：上下文、生成、可见结构与状态变量。', metric: '04 · 配置层级', tags: ['对话覆盖', '账户默认', '全局回退'], coverage: ['预设 / 模板 / 正则 / 世界书 / Author’s Note 绑定', '采样、上下文预算、感知开关和回复长度', '输出契约执行、MVU 变量诊断与能力开关'], fields: ['输出格式　继承账户默认', 'Author’s Note　每 3 楼注入', '状态变量　12 项 · 查看诊断'] },
    { id: 'host', icon: '⌘', short: '卡 UI', name: '角色卡运行时停靠栏', route: '/chat → MVU Host Dock', action: '展开停靠栏', question: '卡片自带界面怎样保持在对话的边缘？', summary: '浏览器 Host 是可折叠的次要表层，既可见又不抢占消息空间。', metric: '02 · 运行时通道', tags: ['MVU', '浏览器同步', '权限'], coverage: ['可渲染卡 UI 的右侧常驻宿主', '本轮变量同步、下行状态与上行持久化', '危险能力授权、运行时日志与降级状态'], fields: ['运行时　已连接', '本回合变量　3 项变更', '危险能力　未授权'] },
  ] },
  studio: { kicker: '创作资产工作台', surfaces: [
    { id: 'persona', icon: '♙', short: '角色', name: '角色卡：从档案到开场', route: '/personas · /personas/:id · /personas/create · /personas/:id/edit', action: '新建角色卡', question: '创作字段、关系和卡兼容性怎样在同一条工作流中出现？', summary: '先用可浏览的角色档案建立选择，再进入分段的卡片编辑。', metric: '08 · 角色资产', tags: ['导入 PNG', '备用开场白', 'MVU'], coverage: ['角色列表、详情、创建、编辑、删除与 PNG 导入导出', '性格 / 背景 / 场景 / 示例 / 标签 / CSS 主题', '默认世界书、Author’s Note、关系与 MVU 兼容报告'], fields: ['伊澜　治愈 · 旧城', '备用开场白　3 条', '默认世界书　旧城档案'] },
    { id: 'world', icon: '⌘', short: '世界书', name: '世界书：管理可激活的设定', route: '/worldbooks · /worldbooks/:id/edit', action: '添加条目', question: '设定条目与可见输出约束怎样不再彼此遮蔽？', summary: '书是容器，条目是可排序的叙事条件；输出契约成为条目旁的可审核标记。', metric: '24 · 条目', tags: ['关键词', '位置', '输出契约'], coverage: ['世界书列表、新建、编辑、导入、导出与删除', '条目关键词、扫描深度、位置、预算与启用状态', '输出契约识别、声明、确认、编辑与恢复自动识别'], fields: ['夜航守则　关键词：船 · 港', '插入位置　角色定义之后', '输出契约　已确认 · 2 个区块'] },
    { id: 'prompt', icon: '✧', short: '预设', name: '预设与 Prompt 模板', route: '/presets · /presets/create · /presets/:id/edit · /templates · /templates/new · /templates/default-view · /templates/:id', action: '新建创作配置', question: '模型参数和 Prompt 结构要如何各自清楚，又能共同编排？', summary: '预设处理“如何生成”，模板处理“如何组装上下文”。', metric: '12 · 可复用配置', tags: ['采样', 'Prompt 顺序', 'Outlet'], coverage: ['预设列表与参数 / Prompt 注入顺序编辑', '模板列表、内置只读模板、首选模板与块编辑', '静态、动态、示例、回复长度、Outlet、Author’s Note 块'], fields: ['叙事长篇　Temperature 0.82', 'Prompt 块　8 个 · 可排序', '回复长度　短 / 中 / 长 已启用'] },
    { id: 'regex', icon: '⌁', short: '正则', name: '正则预设：两条处理管线', route: '/regex-presets · /regex-presets/create · /regex-presets/:id/edit', action: '添加正则脚本', question: '怎样让 Prompt 处理与可见回复处理的差异一眼可辨？', summary: '每条脚本都明确显示处理阶段，避免“看不见的文本改写”。', metric: '06 · 处理脚本', tags: ['Prompt', 'Reply', '启用'], coverage: ['正则预设列表、导入、导出、删除与编辑', '脚本名称、模式、替换内容、启用与排序', 'Prompt-only 与 Reply 显示管线的语义提示'], fields: ['清除思维链标记　Prompt', '角色称呼替换　Reply', '脚本 3 / 6 已启用'] },
  ] },
  insights: { kicker: '记忆与感知', surfaces: [
    { id: 'memory', icon: '▤', short: '记忆', name: '记忆库：筛选、核对与修订', route: '/memories', action: '整理记忆', question: '如何在不把记忆系统变成表格地狱的前提下让人可控？', summary: '先以语义片段阅读，再按类别、作用域与类型收束，编辑保留来源与范围。', metric: '18 · 已提取记忆', tags: ['全局', '角色', '对话'], coverage: ['类别、作用域、类型筛选与分页', '单条编辑、删除与清空全部记忆', '自动提取结果的内容、分类、作用域和类型辨识'], fields: ['偏好　用户喜欢雨夜场景', '关系　伊澜害怕失去承诺', '范围　对话 · 月光落在旧书页上'] },
    { id: 'mood', icon: '◒', short: '情绪', name: '情绪仪表盘：关系中的时间线', route: '/mood', action: '查看本月', question: '怎样把统计图变成能理解的对话感知，而不是监控面板？', summary: '总览、趋势、分布和日历围绕同一个角色/对话筛选器连续协作。', metric: '30 · 最近天数', tags: ['趋势', '分布', '日历'], coverage: ['时间范围、角色与对话的级联筛选', '趋势 / 对话弧线、情绪分布与月度日历', '感知系统关闭时的空状态与说明'], fields: ['范围　伊澜 · 全部对话', '主情绪　平静 42%', '7 月 16 日　温暖 · 7 / 10'] },
    { id: 'bond', icon: '∞', short: '关系', name: '关系：看见一段连接的变化', route: '/personas/:id · /chat', action: '打开角色档案', question: '关系信息何时应该是提示，何时应该成为可深入阅读的档案？', summary: '聊天中只提示当前阶段；角色详情才呈现等级、进度和里程碑历史。', metric: '72% · 熟悉', tags: ['阶段', '阈值', '里程碑'], coverage: ['对话顶部的关系条与感知开关联动', '角色详情中的关系等级、进度、时间与轮次', '里程碑消息与当前情绪的非侵入提示'], fields: ['当前阶段　熟悉', '下个里程碑　还差 8%', '相识　24 天 · 128 轮'] },
  ] },
  account: { kicker: '账户与访问', surfaces: [
    { id: 'profile', icon: '◉', short: '资料', name: '账户偏好：我的默认工作方式', route: '/settings', action: '保存偏好', question: '如何把复杂默认值组织成“我想怎样使用 EMIYA”？', summary: '资料、显示、生成策略与记忆预算按心智模型分区，危险项与日常偏好分开。', metric: '06 · 设置区域', tags: ['资料', '显示偏好', '高级'], coverage: ['邮箱、昵称、头像与全局 CSS 主题', '前端代码块、情感分析默认、MVU 兼容与输出格式默认', '记忆提取 / Query / 矛盾检测、上下文与预算账户默认'], fields: ['昵称　Lenovo', '新对话情感分析　开启', '输出格式执行　跟随全局'] },
    { id: 'security', icon: '◇', short: '安全', name: '安全与登录设备', route: '/settings', action: '检查设备', question: '怎样让安全操作明确、可撤回，并且不打扰日常创作？', summary: '密码、设备会话与不可逆账户操作有清楚的风险阶梯。', metric: '03 · 活跃设备', tags: ['改密码', '会话', '注销'], coverage: ['当前密码校验与密码更新', '当前会话、单设备撤销、撤销其他设备与退出登录', '账户删除的二次确认与明确后果'], fields: ['当前设备　Windows · 刚刚', '其他会话　2 个', '危险区　删除账户'] },
    { id: 'sign-in', icon: '→', short: '登录', name: '访问旅程：欢迎回来', route: '/login · /register · /forgot-password · /reset-password', action: '继续访问', question: '认证页面怎样从“表单”变成清晰、低焦虑的进入体验？', summary: '登录是主入口，注册和重置密码以短路径承接；每一步只要求当前必要的信息。', metric: '04 · 认证页面', tags: ['登录', '注册', '找回'], coverage: ['邮箱 / 密码登录与注册（昵称、确认密码）', '忘记密码邮件请求与 token 重置新密码', '已登录重定向、未授权访问回到登录的状态提示'], fields: ['邮箱　you@example.com', '密码　••••••••', '忘记密码？　发送重置链接'] },
  ] },
}

const config = computed(() => scopes[props.scope])
const active = ref(props.initialSurface || config.value.surfaces[0].id)
const activeSurface = computed(() => config.value.surfaces.find(item => item.id === active.value) || config.value.surfaces[0])
const fixtures: Record<string, Fixture[]> = {
  'conversation/talk': [
    { title: '月光落在旧书页上', meta: '伊澜 · 旧城图书馆 · 12 分钟前', value: '进行中', tone: 'warm' },
    { title: '海雾与来信', meta: '诺娅 · 港口公寓 · 昨天', value: '42 轮', tone: 'cool' },
    { title: '庭院里的下午茶', meta: '阿斯特 · 王都 · 3 天前', value: '已归档', tone: 'plain' },
  ],
  'conversation/start': [
    { title: '伊澜', meta: '角色卡 · 默认携带「旧城档案」', value: 'AI 角色', tone: 'warm' },
    { title: '林川', meta: '用户角色 · 旅行作家', value: '可选', tone: 'cool' },
    { title: '叙事长篇', meta: '预设 + Prompt 模板 + 6 条正则', value: '已预填', tone: 'plain' },
  ],
  'conversation/control': [
    { title: '旧城档案', meta: '世界书 · 18 条启用条目', value: '已绑定', tone: 'warm' },
    { title: '结构化状态栏', meta: '输出契约 · 自动执行', value: '继承', tone: 'cool' },
    { title: 'Author’s Note', meta: '“保持雨夜的克制与温度”', value: '每 3 楼', tone: 'plain' },
  ],
  'conversation/host': [
    { title: '状态面板', meta: '浏览器 MVU Host · 可渲染', value: '已连接', tone: 'warm' },
    { title: '角色状态', meta: '体力 78 · 信任 72 · 金币 36', value: '本轮 +3', tone: 'cool' },
    { title: '能力权限', meta: '读聊天记录 / 读世界书', value: '2 / 5', tone: 'plain' },
  ],
  'studio/persona': [
    { title: '伊澜', meta: '治愈 · 旧城 · 最近对话 12 分钟前', value: '128 轮', tone: 'warm' },
    { title: '诺娅', meta: '港口 · 悬疑 · 2 条备用开场白', value: '42 轮', tone: 'cool' },
    { title: '阿斯特', meta: '王都 · 日常 · MVU 卡', value: '兼容', tone: 'plain' },
  ],
  'studio/world': [
    { title: '旧城档案', meta: '24 条目 · 关键词扫描深度 4', value: '已启用', tone: 'warm' },
    { title: '海港来信', meta: '11 条目 · 2 条输出契约已确认', value: '草稿', tone: 'cool' },
    { title: '王都礼仪', meta: '系统模板 · 8 条目', value: '只读', tone: 'plain' },
  ],
  'studio/prompt': [
    { title: '叙事长篇', meta: 'Temperature 0.82 · 8 个 Prompt 块', value: '首选', tone: 'warm' },
    { title: '短篇对话', meta: 'Temperature 0.65 · 回复长度已关闭', value: '可用', tone: 'cool' },
    { title: '系统默认模板', meta: '内置 · 只读浏览', value: '默认', tone: 'plain' },
  ],
  'studio/regex': [
    { title: '清除思维链标记', meta: 'Prompt 阶段 · 发送给模型前', value: '启用', tone: 'warm' },
    { title: '角色称呼替换', meta: 'Reply 阶段 · 仅显示文本', value: '启用', tone: 'cool' },
    { title: '清理重复空行', meta: 'Reply 阶段 · 排序 #6', value: '停用', tone: 'plain' },
  ],
  'insights/memory': [
    { title: '用户偏好雨夜场景', meta: '偏好 · 全局 · 自动提取于 07/15', value: '高置信', tone: 'warm' },
    { title: '伊澜害怕失去承诺', meta: '关系 · 角色范围 · 来自第 84 轮', value: '已确认', tone: 'cool' },
    { title: '旧书店门口有一盏坏路灯', meta: '设定 · 对话范围 · 可编辑', value: '草稿', tone: 'plain' },
  ],
  'insights/mood': [
    { title: '平静', meta: '过去 30 天 · 17 次出现', value: '42%', tone: 'warm' },
    { title: '温暖', meta: '7 月 16 日 · 与伊澜', value: '7 / 10', tone: 'cool' },
    { title: '担忧', meta: '7 月 13 日 · 海雾与来信', value: '4 / 10', tone: 'plain' },
  ],
  'insights/bond': [
    { title: '熟悉', meta: '当前关系阶段 · 伊澜', value: '72%', tone: 'warm' },
    { title: '初次信任', meta: '里程碑 · 2026/06/29', value: '已达成', tone: 'cool' },
    { title: '共同记忆', meta: '下一个里程碑仍需 8%', value: '待解锁', tone: 'plain' },
  ],
  'account/profile': [
    { title: 'Lenovo', meta: '头像已上传 · 用户级 CSS 已启用', value: '资料', tone: 'warm' },
    { title: '情感分析', meta: '新对话默认开启 · 可按对话覆盖', value: '开启', tone: 'cool' },
    { title: '输出契约', meta: '账户默认：自动执行 · 可改为 strict', value: '自动', tone: 'plain' },
  ],
  'account/security': [
    { title: 'Windows · Chrome', meta: 'Chicago · 当前会话 · 刚刚', value: '当前', tone: 'warm' },
    { title: 'iPhone · Safari', meta: '上次活跃：昨天 21:48', value: '可撤销', tone: 'cool' },
    { title: 'Windows · Edge', meta: '上次活跃：7 月 10 日', value: '可撤销', tone: 'plain' },
  ],
  'account/sign-in': [
    { title: '欢迎回来', meta: '邮箱 + 密码是最短登录路径', value: '登录', tone: 'warm' },
    { title: '新建账户', meta: '邮箱、昵称、密码与确认密码', value: '注册', tone: 'cool' },
    { title: '恢复访问', meta: '邮件链接 → token → 设置新密码', value: '找回', tone: 'plain' },
  ],
}
const records = computed(() => fixtures[`${props.scope}/${active.value}`] || [])
const simulationState = ref('已加载本地虚拟数据 · 未连接后端')
function inspect(title: string) { simulationState.value = `正在查看虚拟记录：「${title}」` }
function advanceState() { simulationState.value = `已模拟操作：「${activeSurface.value.action}」` }
watch(() => props.initialSurface, (next) => {
  if (next && config.value.surfaces.some(item => item.id === next)) active.value = next
}, { immediate: true })
const labels = { A: '工作台', B: '流程板', C: '阅读画布' }
const keys: Variant[] = ['A', 'B', 'C']
const getVariant = (): Variant => { const value = new URLSearchParams(location.search).get('variant'); return keys.includes(value as Variant) ? value as Variant : 'A' }
const variant = ref<Variant>(getVariant())
function setVariant(next: Variant) { variant.value = next; const url = new URL(location.href); url.searchParams.set('variant', next); history.replaceState(null, '', url) }
function keyNav(event: KeyboardEvent) { const target = event.target as HTMLElement | null; if (target?.matches('input, textarea, [contenteditable="true"]')) return; if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return; const index = keys.indexOf(variant.value); setVariant(keys[(index + (event.key === 'ArrowRight' ? 1 : -1) + keys.length) % keys.length]) }
onMounted(() => addEventListener('keydown', keyNav)); onBeforeUnmount(() => removeEventListener('keydown', keyNav))

const SurfaceDetail = { props: { surface: { type: Object, required: true }, records: { type: Array, required: true }, mode: { type: String, required: true } }, emits: ['inspect'], template: `<div class="surface-detail" :class="mode"><div class="fake-form"><label v-for="field in surface.fields" :key="field"><span>{{ field.split('　')[0] }}</span><b>{{ field.split('　').slice(1).join('　') || '已配置' }}</b></label></div><div class="coverage-list"><span v-for="tag in surface.tags" :key="tag">{{ tag }}</span></div><div class="demo-data"><p>虚拟数据 · 点击查看</p><button v-for="record in records" :key="record.title" :class="record.tone" @click="$emit('inspect', record.title)"><span><b>{{ record.title }}</b><small>{{ record.meta }}</small></span><em>{{ record.value }}</em></button></div></div>` }
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Noto+Serif+SC:wght@500;600;700&display=swap');
*{box-sizing:border-box}.prototype{min-height:100vh;font-family:Inter,"Microsoft YaHei",sans-serif;color:#eae4d8;background:#101622}.brand{font-family:"Noto Serif SC",serif;font-size:23px;letter-spacing:.12em;color:#edc27b}.brand span{font-size:12px;color:#c87761;margin-left:7px}button{font:inherit;cursor:pointer}.eyebrow,.desk-header p,.flow-intro>p,.canvas-index p{font:500 11px "DM Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:#c99b61}.accent{border:1px solid #edb478;border-radius:8px;padding:11px 15px;background:#d58565;color:#251715;font-weight:700}.desk{display:grid;grid-template-columns:176px minmax(480px,1fr) 290px;min-height:100vh;background:radial-gradient(circle at 66% 10%,#243b59 0,#111827 45%,#0d121d 100%)}.rail{display:flex;flex-direction:column;padding:31px 16px;border-right:1px solid #ffffff13;background:#0b101acc}.rail-label{margin:54px 10px 12px;color:#7b899d;font-size:11px}.rail>button{display:flex;gap:11px;align-items:center;padding:11px 10px;color:#aeb8c6;text-align:left;border:0;background:transparent;border-radius:7px;font-size:13px}.rail>button i{width:18px;font-style:normal;color:#d4a564}.rail>button:hover,.rail>button.active{color:#fff1d8;background:#d89a6a18}.rail-footer{margin-top:auto;padding:15px 10px 0;border-top:1px solid #ffffff12;color:#7e8a9a;font-size:11px;line-height:1.8}.rail-footer small{color:#b99b72}.desk-content{padding:8vh 5.5vw 90px}.desk-header{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:33px}.desk-header p{margin:0 0 10px}.desk-header h1{margin:0;font:600 clamp(35px,4vw,60px)/1.2 "Noto Serif SC",serif}.desk-context{margin:42px 25px 82px 0;padding:23px;border:1px solid #ecd6af27;border-radius:13px;background:#121a29a8;align-self:stretch}.desk-context p{margin:0;color:#aeb8c5;font-size:11px}.desk-context h2{font:600 27px "Noto Serif SC",serif;color:#efc27a}.desk-context ul{padding-left:18px;color:#b6c1ce;font-size:12px;line-height:1.8}.desk-context li{margin:10px 0}.signal{margin-top:32px;padding-top:16px;border-top:1px solid #ffffff15;color:#aab4c3;font-size:12px}.signal span{color:#a9d88e}.signal small{color:#718094}.surface-detail{display:grid;gap:18px}.fake-form{display:grid;gap:9px}.fake-form label{display:flex;justify-content:space-between;gap:18px;padding:13px 15px;border:1px solid #ead6b422;border-radius:8px;background:#ffffff05;color:#aeb8c7;font-size:12px}.fake-form b{color:#f1e4ce;font-weight:500;text-align:right}.coverage-list{display:flex;gap:7px;flex-wrap:wrap}.coverage-list span,.chip-row span{padding:5px 8px;border:1px solid #d9a66d55;border-radius:99px;color:#e7bc7f;font-size:11px}.flow{min-height:100vh;padding-bottom:100px;background:linear-gradient(135deg,#172331,#0f1521 62%,#1d2936)}.flow-header{display:flex;align-items:center;justify-content:space-between;padding:22px 5vw;border-bottom:1px solid #ffffff15}.flow-header>span{color:#8d9bad;font-size:12px}.flow-tabs{display:flex;gap:5px;max-width:60%;overflow:auto}.flow-tabs button{padding:8px 11px;border:0;border-radius:5px;color:#aeb8c5;background:transparent;font-size:12px;white-space:nowrap}.flow-tabs .active{background:#e2a66e;color:#251915}.flow-intro{max-width:900px;margin:9vh auto 34px;padding:0 5vw}.flow-intro>p{margin:0 0 14px}.flow-intro h1{max-width:700px;margin:0 0 25px;font:600 clamp(35px,5vw,64px)/1.2 "Noto Serif SC",serif}.flow-board{display:grid;grid-template-columns:.8fr 1.05fr 1.15fr;gap:14px;max-width:1160px;margin:auto;padding:0 5vw}.flow-card{min-height:370px;padding:23px;border-radius:13px;border:1px solid #ffffff16}.flow-card>b{font:500 11px "DM Mono",monospace;color:#c89a60;letter-spacing:.08em}.flow-card h2{font:600 25px/1.35 "Noto Serif SC",serif}.flow-card p,.flow-card li{color:#b3bfcc;font-size:13px;line-height:1.8}.discover{background:linear-gradient(160deg,#344c5a,#21303f)}.shape{background:#191d2a}.shape ul{padding-left:17px}.chip-row{display:flex;gap:6px;flex-wrap:wrap;margin-top:22px}.metric{display:inline-block;margin-top:35px;padding:9px 11px;color:#f4d4a1;border:1px solid #f4d4a144;border-radius:6px;font:12px "DM Mono",monospace}.act{display:flex;flex-direction:column;background:#e5ddcf;color:#253041}.act>b{color:#805f39}.act .fake-form label{border-color:#77674d33;background:#fff7ea88;color:#677080}.act .fake-form b{color:#354355}.act .coverage-list span{color:#795833;border-color:#a8783b77}.wide{width:100%;margin-top:auto}.canvas{min-height:100vh;padding-bottom:90px;background:#f4f0e8;color:#263142}.canvas-header{display:flex;align-items:center;justify-content:space-between;padding:22px 5vw;border-bottom:1px solid #c9c0b2}.canvas-header .brand{color:#6f473c}.canvas-header nav{display:flex;gap:15px;overflow:auto}.canvas-header nav button,.canvas-index button{padding:7px;color:#697484;background:transparent;border:0;font-size:12px;white-space:nowrap}.canvas-header nav .active{color:#9b5d4e;border-bottom:2px solid #b87861}.profile{width:31px;height:31px;border:0;border-radius:50%;background:#9b5d4e;color:#fff8ea}.canvas-grid{display:grid;grid-template-columns:190px minmax(400px,1fr) 270px;max-width:1250px;margin:auto}.canvas-index{padding:65px 20px;border-right:1px solid #d5cdc0}.canvas-index p{margin:0 0 19px;color:#8f7658}.canvas-index button{display:block;width:100%;padding:10px 0;text-align:left}.canvas-index button:hover{color:#a35f4d}.canvas-main{max-width:720px;padding:65px 6vw}.canvas-main .eyebrow{margin:0 0 14px;color:#966c49}.canvas-main h1{margin:0;font:600 clamp(38px,5vw,65px)/1.16 "Noto Serif SC",serif}.lead{max-width:560px;margin:25px 0 34px;color:#657184;line-height:1.9}.canvas-main .fake-form label{border-color:#d7cdbd;background:#fffcf7;color:#748090}.canvas-main .fake-form b{color:#3f4c5d}.canvas-main .coverage-list span{border-color:#c8955d;color:#855933}.text-action{margin-top:27px;padding:0;color:#9a5d4f;border:0;background:transparent;font-weight:700}.canvas-notes{margin:64px 0 60px;padding:21px;border-left:1px solid #d5ccbe}.canvas-notes>span{color:#9c7351;font-size:11px}.canvas-notes h2{font:600 22px/1.5 "Noto Serif SC",serif}.canvas-notes p{color:#6d7888;font-size:13px;line-height:1.8}.canvas-notes hr{margin:23px 0;border:0;border-top:1px solid #d6ccbd}.canvas-notes b,.canvas-notes small,.canvas-notes code{display:block;margin-top:11px;font-size:11px}.canvas-notes b{color:#8a674a}.canvas-notes code{color:#5d7287;white-space:normal}.canvas-notes small{color:#6d7888;line-height:1.5}@media(max-width:900px){.desk{grid-template-columns:138px 1fr}.desk-context{display:none}.desk-content{padding:60px 5vw 90px}.flow-board{grid-template-columns:1fr}.flow-card{min-height:auto}.canvas-grid{grid-template-columns:1fr}.canvas-index,.canvas-notes{display:none}.canvas-main{margin:auto;padding:60px 7vw}.canvas-header nav{max-width:55%}}@media(max-width:600px){.rail{display:none}.desk{grid-template-columns:1fr}.desk-header{align-items:flex-start;flex-direction:column}.flow-header{gap:15px}.flow-header>span{display:none}.flow-tabs{max-width:70%}.canvas-header nav{display:none}.fake-form label{flex-direction:column;gap:5px}.fake-form b{text-align:left}}
.demo-data{display:grid;gap:7px;padding-top:4px}.demo-data>p{margin:0 0 1px;color:#8593a5;font:10px "DM Mono",monospace;letter-spacing:.08em;text-transform:uppercase}.demo-data button{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:10px 11px;color:#e5e8eb;text-align:left;border:1px solid #ffffff13;border-radius:7px;background:#ffffff06}.demo-data button:hover{border-color:#e5b77599;transform:translateX(2px)}.demo-data button span{display:grid;gap:3px}.demo-data button b{font-size:12px;font-weight:600}.demo-data button small{color:#94a1b0;font-size:10px}.demo-data button em{padding:3px 6px;color:#dcb06d;background:#dcb06d16;border-radius:99px;font-size:10px;font-style:normal;white-space:nowrap}.demo-data .cool em{color:#9ec8dd;background:#9ec8dd16}.demo-data .plain em{color:#adb5be;background:#adb5be16}.simulation-state{position:fixed;z-index:21;right:22px;bottom:26px;max-width:300px;padding:8px 10px;color:#b9c4d0;border:1px solid #ffffff18;border-radius:7px;background:#101724e8;box-shadow:0 10px 30px #0004;font-size:11px}
.prototype{padding-top:132px}.desk{grid-template-columns:minmax(480px,1fr) 290px}.desk-content{padding-top:7vh}.scope-studio .desk,.scope-studio .flow,.scope-studio .canvas{padding-top:0}@media(max-width:900px){.desk{grid-template-columns:1fr}.desk-context{display:none}}@media(max-width:600px){.simulation-state{right:14px;bottom:69px;max-width:calc(100vw - 28px)}}
</style>
