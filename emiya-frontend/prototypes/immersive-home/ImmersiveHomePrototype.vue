<!--
  PROTOTYPE — “新首页怎样把 EMIYA 已有功能组织成故事入口？”
  Three variants at ?variant=A|B|C. Run: npm run prototype:home (in emiya-frontend).
  This route is read-only and must be deleted or absorbed after a design is selected.
-->
<template>
  <main class="prototype-page" :class="`variant-${currentVariant.toLowerCase()}`">
    <section v-if="currentVariant === 'A'" class="story-desk">
      <div class="desk-main">
        <p class="eyebrow">你的叙事工作台 · 07:42 PM</p>
        <h1>继续一段<br><em>未完的故事</em></h1>
        <p class="intro">把角色、世界与记忆留在身后，把注意力留给当下的相遇。</p>
        <div class="hero-actions">
          <button class="primary" @click="go('/chat')">继续对话 <span>→</span></button>
          <button class="quiet" @click="go('/personas')">选择角色</button>
        </div>

        <section class="shelf" aria-label="最近对话">
          <div class="section-heading"><span>最近章节</span><button @click="go('/chat')">查看全部 →</button></div>
          <button v-for="conversation in conversations" :key="conversation.title" class="chapter" @click="go('/chat')">
            <i :class="conversation.tone"></i>
            <span><b>{{ conversation.title }}</b><small>{{ conversation.meta }}</small></span>
            <time>{{ conversation.time }}</time>
          </button>
        </section>

        <section class="people-shelf" aria-label="角色入口">
          <div class="section-heading"><span>与你同行的人</span><button @click="go('/personas')">管理角色 →</button></div>
          <button v-for="persona in personas" :key="persona.name" class="persona-token" @click="go('/personas')">
            <i :class="`portrait portrait-${persona.tone}`">{{ persona.initial }}</i><span>{{ persona.name }}</span>
          </button>
        </section>
      </div>

      <div class="hero-portrait" aria-label="角色插画占位">
        <div class="moon">☾</div><div class="constellation">✦　·　✧<br>　·　✦　　</div>
        <div class="portrait-frame"><div class="silhouette"></div><span>角色视觉区<br>可接角色卡头像 / 插画</span></div>
        <p>“故事总会在你愿意开口时继续。”</p>
      </div>
    </section>

    <section v-else-if="currentVariant === 'B'" class="orbit-home">
      <header class="orbit-header"><div class="wordmark">EMIYA<span>✦</span></div><div><button @click="go('/settings')">偏好设置</button><button @click="go('/chat')" class="mini-primary">进入对话 →</button></div></header>
      <div class="orbit-stage">
        <div class="orbit-copy"><p class="eyebrow">今天的陪伴</p><h1>让每段关系<br>找到自己的轨道。</h1><p>首页以角色与关系为中心；记忆、心情和世界状态成为可感知但不喧闹的环境。</p></div>
        <div class="orbit-core" @click="go('/chat')" role="button" tabindex="0" @keydown.enter="go('/chat')">
          <span class="orbit-label">正在等你<br><b>伊澜</b></span><div class="portrait portrait-ember huge">伊</div><i class="ring ring-one"></i><i class="ring ring-two"></i>
          <button class="satellite s-one" @click.stop="go('/memories')">▤<small>记忆 18</small></button>
          <button class="satellite s-two" @click.stop="go('/mood')">◒<small>情绪 平静</small></button>
          <button class="satellite s-three" @click.stop="go('/worldbooks')">⌘<small>世界书 2</small></button>
        </div>
        <aside class="bond-card"><p>你和伊澜</p><strong>熟悉 · 72%</strong><div class="meter"><i></i></div><small>认识 24 天 · 128 轮对话</small><button @click="go('/personas')">查看角色档案 →</button></aside>
      </div>
      <footer class="orbit-actions">
        <button @click="go('/chat')"><span>✦</span><b>继续对话</b><small>回到上次的故事</small></button>
        <button @click="go('/personas')"><span>♙</span><b>选择角色</b><small>管理角色卡与开场白</small></button>
        <button @click="go('/worldbooks')"><span>⌘</span><b>展开世界</b><small>管理世界书与设定</small></button>
      </footer>
    </section>

    <section v-else class="chapter-canvas">
      <header class="canvas-top"><div class="wordmark">EMIYA<span>✦</span></div><nav><button @click="go('/chat')">对话</button><button @click="go('/memories')">记忆</button><button @click="go('/mood')">情绪</button><button @click="go('/settings')">设置</button></nav><button class="avatar-dot" @click="go('/settings')">你</button></header>
      <div class="canvas-grid">
        <section class="chapter-intro"><p class="eyebrow">故事总览 / 03</p><h1>今夜，<br>从哪一章开始？</h1><p>让“正在发生的故事”成为首页的主内容；管理能力围绕它展开。</p><button class="primary" @click="go('/chat')">打开当前章节 →</button></section>
        <section class="active-chapter" @click="go('/chat')" role="button" tabindex="0" @keydown.enter="go('/chat')"><div class="chapter-art"><span>Night<br>Archive</span><i></i></div><div class="active-copy"><p>进行中 · 与 伊澜</p><h2>月光落在旧书页上</h2><blockquote>“我想，也许今晚我们可以不急着道别。”</blockquote><span>最后更新于 12 分钟前　→</span></div></section>
        <aside class="context-column"><section><span class="badge">关系</span><h3>熟悉</h3><div class="meter"><i></i></div><p>72% · 下一个里程碑还差 8%</p></section><section><span class="badge">感知</span><h3>平静的夜晚</h3><p>最近 7 轮对话稳定；情绪记录已开启。</p><button @click="go('/mood')">打开情绪面板 →</button></section><section><span class="badge">上下文</span><h3>世界正在生长</h3><p>2 本世界书 · 18 条已提取记忆</p><button @click="go('/worldbooks')">整理设定 →</button></section></aside>
      </div>
      <section class="tool-ribbon"><button @click="go('/personas')"><b>角色</b><span>角色卡、开场白、状态变量</span></button><button @click="go('/memories')"><b>记忆</b><span>提取、检索与管理</span></button><button @click="go('/presets')"><b>创作工作台</b><span>预设、模板、正则</span></button><button @click="go('/worldbooks')"><b>世界书</b><span>关键词与输出契约</span></button></section>
    </section>

    <aside class="prototype-note"><b>原型状态</b><span>{{ currentVariant }} · {{ variantDescription }}</span><small>只读展示 · 对应正式入口：{{ selectedTarget }}</small></aside>
    <PrototypeVariantSwitcher :current="currentVariant" @change="setVariant" />
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import PrototypeVariantSwitcher from './PrototypeVariantSwitcher.vue'

type VariantKey = 'A' | 'B' | 'C'
const emit = defineEmits<{ navigate: [path: string] }>()

const variantKeys: VariantKey[] = ['A', 'B', 'C']
const conversations = [
  { title: '月光落在旧书页上', meta: '伊澜 · 旧城图书馆', time: '12 分钟前', tone: 'ember' },
  { title: '海雾与来信', meta: '诺娅 · 海港', time: '昨天', tone: 'mist' },
  { title: '庭院里的下午茶', meta: '阿斯特 · 王都', time: '3 天前', tone: 'gold' },
]
const personas = [
  { name: '伊澜', initial: '伊', tone: 'ember' },
  { name: '诺娅', initial: '诺', tone: 'mist' },
  { name: '阿斯特', initial: '阿', tone: 'gold' },
]
const descriptions: Record<VariantKey, string> = {
  A: '故事书桌：以继续对话与最近章节为第一优先级。',
  B: '关系轨道：以角色、关系、记忆和情绪的关联为第一优先级。',
  C: '章节画布：以正在进行的故事和上下文状态为第一优先级。',
}

const featureTargets: Record<string, string> = {
  '/chat': '对话页 /chat',
  '/personas': '角色管理 /personas',
  '/memories': '记忆面板 /memories',
  '/mood': '情绪仪表盘 /mood',
  '/worldbooks': '世界书 /worldbooks',
  '/presets': '预设工作台 /presets',
  '/settings': '账户设置 /settings',
}

function readVariant(): VariantKey {
  const candidate = new URLSearchParams(window.location.search).get('variant') || 'A'
  return variantKeys.includes(candidate as VariantKey) ? candidate as VariantKey : 'A'
}

const currentVariant = ref<VariantKey>(readVariant())
const selectedTarget = ref('尚未选择')
const variantDescription = computed(() => descriptions[currentVariant.value])

function setVariant(variant: VariantKey) {
  currentVariant.value = variant
  const url = new URL(window.location.href)
  url.searchParams.set('variant', variant)
  window.history.replaceState(null, '', url)
}

function go(path: string) {
  selectedTarget.value = featureTargets[path] || path
  emit('navigate', path)
}

function handleArrow(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  if (target?.matches('input, textarea, [contenteditable="true"]')) return
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  const index = variantKeys.indexOf(currentVariant.value)
  const delta = event.key === 'ArrowRight' ? 1 : -1
  setVariant(variantKeys[(index + delta + variantKeys.length) % variantKeys.length])
}

onMounted(() => window.addEventListener('keydown', handleArrow))
onBeforeUnmount(() => window.removeEventListener('keydown', handleArrow))
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Noto+Serif+SC:wght@500;600;700&display=swap');

.prototype-page { min-height: 100vh; color: #f7efe2; background: #0b111b; font-family: Inter, "Microsoft YaHei", sans-serif; }
button { font: inherit; } button:not(.prototype-switcher button) { color: inherit; cursor: pointer; }
.wordmark { color: #efc27c; font-family: "Noto Serif SC", serif; font-size: 23px; letter-spacing: .08em; }.wordmark span { margin-left: 8px; color: #bc735d; font-size: 13px; }
.eyebrow { margin: 0 0 14px; color: #d8a764; font-family: "DM Mono", monospace; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; }
.primary { padding: 13px 20px; color: #25150f; background: #ce7a60; border: 1px solid #ed9b7f; border-radius: 9px; font-weight: 700; }.primary span { margin-left: 18px; }
.meter { height: 7px; overflow: hidden; background: rgba(229, 219, 196, .14); border-radius: 99px; }.meter i { display: block; width: 72%; height: 100%; background: linear-gradient(90deg, #c7735c, #e8bd75); border-radius: inherit; }

/* A — an editorial desk, closest to the generated visual direction. */
.story-desk { display: grid; min-height: 100vh; grid-template-columns: 156px minmax(470px, 1fr) minmax(360px, .8fr); background: radial-gradient(circle at 72% 30%, #182945 0, #0b121e 48%); }.rail { display: flex; flex-direction: column; padding: 34px 20px 24px; border-right: 1px solid rgba(220, 181, 114, .18); background: rgba(7, 13, 23, .4); }.rail nav { display: grid; gap: 9px; margin-top: 80px; }.rail nav button, .rail-settings { padding: 10px 8px; color: #a6adbc; text-align: left; background: transparent; border: 0; border-radius: 7px; font-size: 13px; }.rail nav button span { display: inline-block; width: 25px; color: #dca967; font-size: 16px; }.rail nav button:hover, .rail nav .active { color: #fff0d8; background: rgba(214, 166, 96, .13); }.rail-settings { margin-top: auto; border-top: 1px solid rgba(220, 181, 114, .14); border-radius: 0; }.desk-main { max-width: 690px; padding: 11vh 8vw 80px; }.desk-main h1 { margin: 0; font-family: "Noto Serif SC", serif; font-size: clamp(44px, 5vw, 72px); line-height: 1.13; letter-spacing: .03em; }.desk-main h1 em { color: #e4b36f; font-style: normal; }.intro { max-width: 380px; margin: 24px 0 28px; color: #9fa8b6; line-height: 1.9; }.hero-actions { display: flex; gap: 12px; }.quiet { padding: 12px 16px; color: #dac9ac; background: transparent; border: 1px solid rgba(225, 203, 163, .26); border-radius: 9px; }.shelf, .people-shelf { margin-top: 52px; }.section-heading { display: flex; justify-content: space-between; margin-bottom: 12px; color: #e9e0d1; font-family: "Noto Serif SC", serif; }.section-heading button { color: #c89b5b; background: transparent; border: 0; font-size: 12px; }.chapter { display: flex; align-items: center; width: 100%; gap: 13px; padding: 12px 0; color: #d9dbe0; text-align: left; background: transparent; border: 0; border-bottom: 1px solid rgba(226, 227, 230, .1); }.chapter:hover { background: rgba(255, 255, 255, .035); }.chapter i { width: 29px; height: 29px; border: 1px solid rgba(225, 183, 111, .45); border-radius: 50%; }.chapter .ember { background: #a55e4d; }.chapter .mist { background: #71869e; }.chapter .gold { background: #ad8952; }.chapter span { flex: 1; }.chapter b, .chapter small { display: block; }.chapter small { margin-top: 4px; color: #7f8998; font-size: 11px; }.chapter time { color: #7f8998; font-size: 11px; }.people-shelf { display: flex; flex-wrap: wrap; gap: 13px; }.people-shelf .section-heading { flex-basis: 100%; }.persona-token { display: grid; gap: 7px; padding: 0; color: #d6c8b7; background: none; border: 0; text-align: center; font-size: 12px; }.portrait { display: grid; width: 46px; height: 46px; place-items: center; color: #ffe6c2; border: 1px solid rgba(234, 195, 124, .72); border-radius: 50%; box-shadow: inset 0 0 0 4px rgba(9, 15, 25, .5); font-family: "Noto Serif SC", serif; font-size: 18px; }.portrait-ember { background: linear-gradient(135deg, #3c2733, #a95b4c); }.portrait-mist { background: linear-gradient(135deg, #263547, #9aaac2); }.portrait-gold { background: linear-gradient(135deg, #493222, #b79757); }.hero-portrait { position: relative; display: flex; flex-direction: column; justify-content: center; min-height: 620px; padding: 64px; overflow: hidden; border-left: 1px solid rgba(220, 181, 114, .18); background: linear-gradient(150deg, rgba(37, 38, 49, .5), rgba(6, 13, 21, .2)); }.moon { position: absolute; top: 11%; right: 18%; color: #f4dfad; font-size: 72px; }.constellation { position: absolute; top: 19%; left: 10%; color: rgba(225, 180, 105, .46); line-height: 2.2; }.portrait-frame { position: relative; width: min(100%, 360px); aspect-ratio: .72; overflow: hidden; border: 1px solid rgba(224, 180, 105, .7); background: linear-gradient(145deg, #1f2f43, #2c1d22 65%, #101722); box-shadow: 0 20px 50px rgba(0,0,0,.4); }.portrait-frame::before { position: absolute; inset: 0; content: ""; background: repeating-linear-gradient(90deg, transparent 0 42px, rgba(231, 180, 98, .08) 43px 44px); }.silhouette { position: absolute; bottom: -15%; left: 22%; width: 58%; height: 80%; border-radius: 50% 50% 35% 35%; background: radial-gradient(circle at 53% 23%, #efb384 0 12%, #2d1a1e 13% 32%, transparent 33%), linear-gradient(135deg, #452029, #0d111b 70%); }.portrait-frame span { position: absolute; right: 14px; bottom: 14px; color: rgba(255, 239, 213, .7); font-size: 11px; line-height: 1.6; }.hero-portrait > p { width: min(100%, 360px); margin: 20px 0 0; color: #b8a896; font-family: "Noto Serif SC", serif; font-size: 13px; line-height: 1.7; }

/* B — a relationship-first orbit with no sidebar or feed. */
.orbit-home { min-height: 100vh; overflow: hidden; background: radial-gradient(circle at 50% 48%, #273452 0, #111a2d 36%, #080d16 74%); }.orbit-header, .canvas-top { display: flex; align-items: center; justify-content: space-between; padding: 27px 5vw; }.orbit-header > div:last-child { display: flex; gap: 10px; }.orbit-header button { padding: 9px 12px; color: #b9c1cf; background: transparent; border: 1px solid rgba(232, 224, 208, .17); border-radius: 7px; font-size: 12px; }.orbit-header .mini-primary { color: #20130f; background: #e2a677; border-color: #e2a677; }.orbit-stage { position: relative; display: grid; grid-template-columns: 1fr minmax(400px, .95fr) 1fr; align-items: center; min-height: 64vh; padding: 30px 8vw; }.orbit-copy { max-width: 360px; }.orbit-copy h1 { margin: 0 0 20px; font-family: "Noto Serif SC", serif; font-size: clamp(34px, 4.5vw, 62px); line-height: 1.22; }.orbit-copy p:last-child { color: #a3afc0; line-height: 1.9; }.orbit-core { position: relative; width: min(50vw, 460px); aspect-ratio: 1; place-self: center; cursor: pointer; }.orbit-core::after { position: absolute; inset: 32%; content: ""; border-radius: 50%; background: radial-gradient(circle, rgba(235, 174, 109, .58), rgba(168, 91, 86, .25) 42%, transparent 70%); filter: blur(16px); }.huge { position: absolute; z-index: 2; top: 31%; left: 31%; width: 38%; height: 38%; font-size: 43px; }.orbit-label { position: absolute; z-index: 3; top: 44%; left: 43%; color: #fff0d7; font-size: 12px; text-align: center; }.orbit-label b { display: block; margin-top: 4px; color: #e9bb75; font-family: "Noto Serif SC", serif; font-size: 20px; }.ring { position: absolute; z-index: 1; border: 1px solid rgba(231, 190, 115, .38); border-radius: 50%; }.ring-one { inset: 15%; }.ring-two { inset: 2%; border-color: rgba(124, 155, 199, .32); }.satellite { position: absolute; z-index: 4; display: grid; width: 82px; height: 82px; place-items: center; color: #e8c17c; background: #111a2b; border: 1px solid rgba(232, 193, 124, .45); border-radius: 50%; box-shadow: 0 10px 28px rgba(0,0,0,.25); font-size: 23px; }.satellite small { color: #aab4c0; font-size: 9px; }.s-one { top: 5%; left: 9%; }.s-two { right: -4%; bottom: 19%; }.s-three { bottom: 1%; left: 13%; }.bond-card { justify-self: end; max-width: 255px; padding: 23px; border: 1px solid rgba(230, 215, 183, .2); border-radius: 13px; background: rgba(12, 20, 34, .68); box-shadow: 0 15px 40px rgba(0,0,0,.16); }.bond-card p { margin: 0 0 12px; color: #aeb8c7; font-size: 12px; }.bond-card strong { display: block; margin-bottom: 14px; color: #f1d59d; font-family: "Noto Serif SC", serif; font-size: 22px; }.bond-card small { display: block; margin: 10px 0 15px; color: #8792a2; }.bond-card button, .context-column button { padding: 0; color: #e3ad69; background: none; border: 0; font-size: 12px; }.orbit-actions { display: flex; justify-content: center; gap: 18px; padding: 15px 5vw 80px; }.orbit-actions > button { display: grid; grid-template-columns: 38px 1fr; width: min(29vw, 290px); gap: 0 10px; padding: 16px; color: #d9dfeb; text-align: left; background: rgba(255,255,255,.035); border: 1px solid rgba(226, 220, 208, .14); border-radius: 12px; }.orbit-actions > button:hover { border-color: rgba(227, 176, 100, .65); transform: translateY(-2px); }.orbit-actions span { grid-row: 1 / 3; color: #e5ad68; font-size: 23px; }.orbit-actions small { margin-top: 5px; color: #8995a6; }

/* C — an active-story canvas with a compact management ribbon. */
.chapter-canvas { min-height: 100vh; padding-bottom: 90px; background: #f2eee6; color: #273243; }.canvas-top { color: #273243; border-bottom: 1px solid #d7d0c5; }.canvas-top .wordmark { color: #6e453a; }.canvas-top nav { display: flex; gap: 22px; }.canvas-top nav button { color: #576273; background: transparent; border: 0; font-size: 13px; }.canvas-top nav button:hover { color: #a35f4d; }.avatar-dot { width: 34px; height: 34px; color: #fff4e8; background: #a35f4d; border: 0; border-radius: 50%; font-size: 12px; }.canvas-grid { display: grid; grid-template-columns: .82fr 1.28fr .7fr; gap: 36px; align-items: center; max-width: 1420px; min-height: calc(100vh - 160px); padding: 45px 7vw; margin: auto; }.chapter-intro h1 { margin: 0 0 20px; color: #303a4b; font-family: "Noto Serif SC", serif; font-size: clamp(38px, 4.6vw, 68px); line-height: 1.18; }.chapter-intro p:not(.eyebrow) { max-width: 280px; color: #6e7886; line-height: 1.8; }.chapter-intro .primary { margin-top: 16px; }.active-chapter { overflow: hidden; cursor: pointer; background: #fffdf8; border: 1px solid #d9cfc0; box-shadow: 0 18px 45px rgba(78, 67, 50, .12); }.active-chapter:hover { transform: translateY(-3px); }.chapter-art { position: relative; height: 250px; padding: 28px; overflow: hidden; color: #f7e8ce; background: linear-gradient(145deg, #17243a, #6a3937 75%, #d58c5a); font-family: "DM Mono", monospace; font-size: 19px; line-height: 1.2; }.chapter-art::before { position: absolute; inset: 0; content: ""; background: radial-gradient(circle at 74% 24%, #f6dfaa 0 5%, transparent 5.5%), radial-gradient(circle at 35% 87%, rgba(0,0,0,.42), transparent 42%); }.chapter-art i { position: absolute; right: 18%; bottom: -20%; width: 38%; height: 76%; border: 1px solid rgba(255,236,198,.5); border-radius: 50% 50% 0 0; }.active-copy { padding: 24px; }.active-copy p, .active-copy span { color: #a25e4e; font-size: 12px; }.active-copy h2 { margin: 9px 0 15px; font-family: "Noto Serif SC", serif; font-size: 27px; }.active-copy blockquote { margin: 0 0 18px; color: #697484; font-family: "Noto Serif SC", serif; font-size: 14px; line-height: 1.7; }.context-column { display: grid; gap: 14px; }.context-column section { padding: 18px; border-left: 2px solid #bd7964; background: #e7e1d7; }.context-column section:nth-child(2) { border-left-color: #717e9c; }.context-column section:nth-child(3) { border-left-color: #b59154; }.badge { color: #a35f4d; font-family: "DM Mono", monospace; font-size: 10px; letter-spacing: .12em; }.context-column h3 { margin: 8px 0; font-family: "Noto Serif SC", serif; font-size: 21px; }.context-column p { color: #6d7682; font-size: 12px; line-height: 1.7; }.context-column .meter { margin: 12px 0; background: #d2c7b6; }.tool-ribbon { display: grid; grid-template-columns: repeat(4, 1fr); max-width: 1420px; margin: 0 auto; border: 1px solid #d7d0c5; }.tool-ribbon button { display: grid; gap: 6px; min-height: 80px; padding: 17px 22px; text-align: left; background: transparent; border: 0; border-right: 1px solid #d7d0c5; }.tool-ribbon button:last-child { border: 0; }.tool-ribbon button:hover { background: #fffaf2; }.tool-ribbon b { color: #3c4656; font-family: "Noto Serif SC", serif; }.tool-ribbon span { color: #7a8491; font-size: 11px; }

.prototype-note { position: fixed; z-index: 10; right: 20px; bottom: 19px; display: grid; gap: 4px; max-width: 300px; padding: 10px 13px; color: #d9dfeb; background: rgba(9, 14, 23, .78); border: 1px solid rgba(255,255,255,.15); border-radius: 8px; font-size: 11px; backdrop-filter: blur(10px); }.prototype-note b { color: #e5b574; }.prototype-note small { color: #8e9aab; }
@media (max-width: 1050px) { .story-desk { grid-template-columns: 126px 1fr; }.hero-portrait { display: none; }.orbit-stage { grid-template-columns: 1fr; gap: 30px; }.orbit-copy, .bond-card { justify-self: center; text-align: center; }.orbit-core { width: min(80vw, 460px); }.canvas-grid { grid-template-columns: 1fr; }.chapter-intro { text-align: center; }.chapter-intro p:not(.eyebrow) { margin-left: auto; margin-right: auto; }.context-column { grid-template-columns: repeat(3, 1fr); }.tool-ribbon { margin: 0 4vw; }.prototype-note { display: none; } }
@media (max-width: 680px) { .story-desk { display: block; }.rail { display: none; }.desk-main { padding: 70px 8vw 95px; }.orbit-actions, .context-column, .tool-ribbon { grid-template-columns: 1fr; flex-wrap: wrap; }.orbit-actions > button { width: 100%; }.context-column { display: grid; }.canvas-top nav { display: none; }.tool-ribbon { display: grid; }.prototype-switcher { bottom: 12px; } }
.prototype-page{padding-top:76px}.story-desk{grid-template-columns:minmax(470px,1fr) minmax(360px,.8fr)}@media(max-width:1050px){.story-desk{grid-template-columns:1fr}}
</style>
