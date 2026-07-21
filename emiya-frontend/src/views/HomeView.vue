<!--
  首页 / 落地页（问题 4）。参照 prototypes/immersive-home 的「章节画布」方案（变体 C），
  全部走 variables.css 令牌、适配日/夜。三列：左叙事引导 + 中英雄卡（最近一段对话）+
  右自适应上下文列（最近其它对话 / 记忆 / 关系·感知·加映），下方工具条。
-->
<template>
  <div class="home">
    <div class="home-grid">
      <!-- 左：叙事引导 -->
      <section class="intro">
        <p class="eyebrow">{{ greeting }} · 你的叙事工作台</p>
        <h1 v-if="featured">从哪一章<br>继续？</h1>
        <h1 v-else>开始你的<br>第一段故事</h1>
        <p class="intro-lead" v-if="featured">把角色、世界与记忆留在身后，把注意力留给当下的相遇。</p>
        <p class="intro-lead" v-else>先选一位角色，开启属于你们的故事。</p>
        <button v-if="featured" class="primary" type="button" @click="openFeatured">打开当前章节 <span aria-hidden="true">→</span></button>
        <button v-else class="primary" type="button" @click="go('/personas')">选择角色 <span aria-hidden="true">→</span></button>
      </section>

      <!-- 中：英雄卡（最近一段对话）/ 空状态 -->
      <section
        v-if="featured"
        class="active-chapter"
        role="button"
        tabindex="0"
        @click="openFeatured"
        @keydown.enter="openFeatured"
      >
        <div class="cover" :style="coverStyle">
          <span class="cover-tag">进行中 · 与 {{ featured.persona_name || 'EMIYA' }}</span>
        </div>
        <div class="chapter-body">
          <h2 class="chapter-title">{{ featured.title || '新对话' }}</h2>
          <blockquote v-if="featured.last_message_preview" class="chapter-quote">
            “{{ featured.last_message_preview }}”
          </blockquote>
          <p v-else class="chapter-quote muted">还没有对话内容，点开继续书写。</p>
          <span class="chapter-foot">最后更新于 {{ relativeTime(featured.updated_at) }}　→</span>
        </div>
      </section>
      <section v-else-if="!convStore.loading" class="active-chapter empty">
        <div class="empty-inner">
          <div class="empty-mark" aria-hidden="true">✦</div>
          <h2>还没有开始任何故事</h2>
          <p>选一位角色，或直接新建一段对话。</p>
          <div class="empty-actions">
            <button class="primary" type="button" @click="go('/personas')">选择角色</button>
            <button class="quiet" type="button" @click="newConversation">新建对话</button>
          </div>
        </div>
      </section>
      <section v-else class="active-chapter skeleton" aria-hidden="true"></section>

      <!-- 右：自适应上下文列 -->
      <aside class="context-col" aria-label="上下文">
        <!-- 最近其它对话（弹性长高，吸收余高，使右列与中列等高） -->
        <section class="ctx-card recent">
          <div class="ctx-head"><span class="badge">最近对话</span></div>
          <div v-if="otherRecent.length" class="recent-list">
            <button
              v-for="conv in otherRecent"
              :key="conv.id"
              type="button"
              class="recent-row"
              @click="openConversation(conv.id)"
            >
              <img
                v-if="convStore.personaAvatarUrl(conv.persona_id)"
                class="recent-avatar"
                :src="convStore.personaAvatarUrl(conv.persona_id)!"
                :alt="conv.persona_name || 'AI'"
              />
              <span
                v-else
                class="recent-avatar fallback"
                :style="{ background: avatarColor(conv.persona_name || 'AI') }"
              >{{ (conv.persona_name || 'AI')[0] }}</span>
              <span class="recent-copy">
                <b>{{ conv.title || '新对话' }}</b>
                <small v-if="conv.last_message_preview">{{ conv.last_message_preview }}</small>
                <small v-else class="muted">暂无内容</small>
              </span>
              <time>{{ relativeTime(conv.updated_at) }}</time>
            </button>
          </div>
          <p v-else class="ctx-empty">还没有其它对话。</p>
        </section>

        <!-- 记忆（通用常在） -->
        <section class="ctx-card">
          <div class="ctx-head"><span class="badge">记忆</span></div>
          <h3 class="ctx-metric">{{ memoryTotal === null ? '—' : memoryTotal }} 条已提取</h3>
          <p v-if="latestMemory" class="ctx-note">{{ latestMemory }}</p>
          <p v-else class="ctx-note muted">暂无记忆，对话中会自动提取。</p>
          <button class="text-action" type="button" @click="go('/memories')">整理记忆 →</button>
        </section>

        <!-- 加映：关系+感知（开且有关系）→ 世界书（有绑定）→ 都没有则省略 -->
        <section v-if="showRelationship && relationship" class="ctx-card">
          <div class="ctx-head"><span class="badge">关系</span></div>
          <h3 class="ctx-metric">{{ relationship.level_name }}</h3>
          <div class="meter"><i :style="{ width: relationship.affinity_score + '%' }"></i></div>
          <p class="ctx-note">{{ relationship.affinity_score }}% · 相识 {{ relationship.days_span }} 天</p>
        </section>
        <section v-else-if="showWorldbook" class="ctx-card">
          <div class="ctx-head"><span class="badge">世界书</span></div>
          <h3 class="ctx-metric">{{ featuredWorldbookCount }} 本已绑定</h3>
          <button class="text-action" type="button" @click="go('/worldbooks')">整理设定 →</button>
        </section>
      </aside>
    </div>

    <!-- 底部工具条：高频入口 -->
    <nav class="tool-ribbon" aria-label="快速入口">
      <button type="button" @click="newConversation"><b>新建对话</b><span>开启一段新的相遇</span></button>
      <button type="button" @click="go('/personas')"><b>角色</b><span>角色卡、开场白、状态变量</span></button>
      <button type="button" @click="go('/memories')"><b>记忆</b><span>提取、检索与管理</span></button>
      <button type="button" @click="go('/worldbooks')"><b>世界书</b><span>关键词与输出契约</span></button>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useConversationStore } from '../stores/conversation'
import { useChatUiStore } from '../stores/chatUi'
import { avatarColor } from '../utils/avatar'
import { fetchMemories } from '../api/memory'
import { fetchConversationRelationship } from '../api/relationship'
import type { Conversation, Relationship } from '../types'

const router = useRouter()
const authStore = useAuthStore()
const convStore = useConversationStore()
const chatUi = useChatUiStore()

// 最近更新那段（后端 list 已按 updated_at desc 排）
const featured = computed<Conversation | null>(() => convStore.list[0] ?? null)
const otherRecent = computed(() =>
  convStore.list.filter((c) => c.id !== featured.value?.id).slice(0, 3),
)

const memoryTotal = ref<number | null>(null)
const latestMemory = ref<string | null>(null)
const relationship = ref<Relationship | null>(null)

const featuredAvatar = computed(() => convStore.personaAvatarUrl(featured.value?.persona_id ?? null))
const coverStyle = computed(() => {
  const url = featuredAvatar.value
  if (url) {
    return { backgroundImage: `linear-gradient(180deg, rgba(37,25,20,0.05), rgba(37,25,20,0.66)), url(${url})` }
  }
  const c = avatarColor(featured.value?.persona_name || 'EMIYA')
  return { background: `linear-gradient(150deg, ${c}, rgba(37,25,20,0.82))` }
})

// 感知开关（对话级 analyze_emotion；ADR-0020）—— 关系/感知卡的前置条件
const perceptionOn = computed(() => featured.value?.analyze_emotion !== false)
const showRelationship = computed(() => perceptionOn.value && !!relationship.value)
const featuredWorldbookCount = computed(() => featured.value?.worldbook_ids?.length ?? 0)
const showWorldbook = computed(() => !showRelationship.value && featuredWorldbookCount.value > 0)

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 11) return '清晨好'
  if (h < 14) return '午间好'
  if (h < 18) return '午后好'
  if (h < 23) return '夜色渐浓'
  return '夜深了'
})

function relativeTime(dateStr: string): string {
  const time = new Date(dateStr).getTime()
  if (!Number.isFinite(time)) return ''
  const diff = Math.max(0, Date.now() - time)
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}天前`
  return new Date(dateStr).toLocaleDateString()
}

function openFeatured() {
  if (!featured.value) return
  openConversation(featured.value.id)
}
function openConversation(id: string) {
  convStore.setCurrent(id)
  router.push('/chat')
}
async function newConversation() {
  await router.push('/chat')
  // 等 ChatView 挂载好 NewConversationDialog（它 watch newConvSignal，无 immediate），再发信号
  await nextTick()
  chatUi.requestNewConv()
}
function go(path: string) {
  router.push(path)
}

onMounted(async () => {
  if (!authStore.user) {
    authStore.initFromStorage()
    try {
      await authStore.fetchMe()
    } catch {
      router.push('/login')
      return
    }
  }
  await Promise.all([
    convStore.list.length ? Promise.resolve() : convStore.fetchList(),
    Object.keys(convStore.personaAvatarById).length ? Promise.resolve() : convStore.fetchPersonaAvatars(),
  ])
  try {
    const res = await fetchMemories(undefined, undefined, undefined, 1, 0)
    memoryTotal.value = res.total
    latestMemory.value = res.items[0]?.content ?? null
  } catch {
    memoryTotal.value = null
  }
  if (featured.value && perceptionOn.value) {
    try {
      relationship.value = await fetchConversationRelationship(featured.value.id)
    } catch {
      relationship.value = null
    }
  }
})
</script>

<style scoped>
.home {
  /* App.vue 的 .app-body 已为无副导航的 /home 加了 var(--nav-offset) 顶部留白，此处不再重复 */
  min-height: calc(100dvh - var(--nav-offset));
  box-sizing: border-box;
  padding: 12px clamp(20px, 6vw, 96px) 40px;
  background: var(--color-bg-page);
}
.home-grid {
  display: grid;
  grid-template-columns: 0.82fr 1.28fr 0.78fr;
  gap: clamp(20px, 3vw, 44px);
  align-items: stretch;
  max-width: 1440px;
  margin: 0 auto;
  min-height: min(66vh, 560px);
}

/* 左：叙事引导 */
.intro { align-self: center; }
.eyebrow {
  margin: 0 0 16px;
  color: var(--color-eyebrow);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.intro h1 {
  margin: 0 0 20px;
  font: 600 clamp(34px, 4vw, 58px)/1.16 var(--font-serif);
  color: var(--color-text);
  letter-spacing: 0.02em;
}
.intro-lead {
  max-width: 300px;
  margin: 0 0 26px;
  color: var(--color-text-secondary);
  line-height: 1.9;
}
.primary {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 13px 22px;
  color: #fffaf4;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--color-primary);
  font: 600 14px var(--font-sans);
  cursor: pointer;
  transition: background var(--transition-fast), transform var(--transition-fast);
}
.primary:hover { background: var(--color-primary-hover); transform: translateY(-1px); }
.primary:active { background: var(--color-primary-pressed); transform: translateY(1px); }
.quiet {
  padding: 13px 20px;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: transparent;
  font: 600 14px var(--font-sans);
  cursor: pointer;
  transition: border-color var(--transition-fast), color var(--transition-fast);
}
.quiet:hover { color: var(--color-primary); border-color: var(--color-primary); }

/* 中：英雄卡 */
.active-chapter {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface-2);
  box-shadow: var(--shadow-md);
  cursor: pointer;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}
.active-chapter:hover { transform: translateY(-3px); box-shadow: var(--shadow-lg); }
.active-chapter:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.cover {
  position: relative;
  /* 主卡被右列撑高后，封面弹性吃掉多余竖向空间，让竖幅立绘显示得更完整、底部不留空 */
  flex: 1;
  min-height: clamp(180px, 26vh, 280px);
  background-size: cover;
  /* 立绘的脸/头通常在顶部——锚定顶部，避免 center 把头裁掉 */
  background-position: top center;
}
.cover-tag {
  position: absolute;
  left: 18px;
  bottom: 14px;
  padding: 5px 11px;
  color: #fff4e8;
  border-radius: var(--radius-pill);
  background: rgba(37, 25, 20, 0.42);
  backdrop-filter: blur(4px);
  font-size: 12px;
}
.chapter-body { padding: 20px 24px 24px; }
.chapter-title { margin: 0 0 14px; font: 600 clamp(20px, 2vw, 27px) var(--font-serif); color: var(--color-text); }
.chapter-quote {
  margin: 0 0 18px;
  color: var(--color-text-secondary);
  font: 15px/1.75 var(--font-serif);
  border-left: 2px solid var(--accent-strong);
  padding-left: 14px;
}
.chapter-quote.muted { color: var(--color-text-tertiary); }
.chapter-foot { color: var(--color-primary); font-size: 13px; }

/* 空状态 / 骨架 */
.active-chapter.empty,
.active-chapter.skeleton { cursor: default; justify-content: center; align-items: center; }
.active-chapter.empty:hover { transform: none; box-shadow: var(--shadow-md); }
.active-chapter.skeleton { min-height: 320px; box-shadow: var(--shadow-sm); }
.empty-inner { padding: 40px; text-align: center; }
.empty-mark { font-size: 34px; color: var(--accent-strong); }
.empty-inner h2 { margin: 14px 0 8px; font: 600 24px var(--font-serif); color: var(--color-text); }
.empty-inner p { margin: 0 0 22px; color: var(--color-text-secondary); }
.empty-actions { display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; }

/* 右：上下文列 */
.context-col { display: flex; flex-direction: column; gap: 14px; align-self: stretch; min-width: 0; }
.ctx-card {
  padding: 18px 20px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-sm);
}
.ctx-card.recent { flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0; }
.ctx-head { margin-bottom: 12px; }
.badge {
  color: var(--color-eyebrow);
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.ctx-metric { margin: 0 0 10px; font: 600 21px var(--font-serif); color: var(--color-text); }
.ctx-note { margin: 0; color: var(--color-text-secondary); font-size: 12px; line-height: 1.7; }
.ctx-note.muted { color: var(--color-text-tertiary); }
.meter { height: 7px; overflow: hidden; margin: 6px 0 10px; background: var(--color-primary-light); border-radius: var(--radius-pill); }
.meter i { display: block; height: 100%; background: linear-gradient(90deg, var(--color-primary), var(--accent-strong)); border-radius: inherit; }
.text-action { margin-top: 12px; padding: 0; color: var(--color-primary); border: 0; background: none; font-size: 12px; font-weight: 600; cursor: pointer; }
.text-action:hover { color: var(--color-primary-hover); }

.recent-list { display: flex; flex-direction: column; gap: 4px; overflow-y: auto; }
.recent-row {
  display: flex;
  align-items: center;
  gap: 11px;
  width: 100%;
  padding: 9px 8px;
  color: inherit;
  text-align: left;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  transition: background var(--transition-fast), transform var(--transition-fast);
}
.recent-row:hover { background: var(--color-primary-bg); transform: translateX(2px); }
.recent-avatar { flex: none; width: 34px; height: 34px; border-radius: 50%; object-fit: cover; }
.recent-avatar.fallback { display: grid; place-items: center; color: #fffaf4; font-family: var(--font-serif); }
.recent-copy { display: grid; flex: 1; min-width: 0; gap: 2px; }
.recent-copy b { font-size: 13px; font-weight: 600; color: var(--color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-copy small { font-size: 11px; color: var(--color-text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-copy small.muted { color: var(--color-text-tertiary); }
.recent-row time { flex: none; color: var(--color-text-tertiary); font-size: 10px; white-space: nowrap; }
.ctx-empty { margin: 0; color: var(--color-text-tertiary); font-size: 12px; }

/* 底部工具条 */
.tool-ribbon {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  max-width: 1440px;
  margin: clamp(24px, 4vh, 48px) auto 0;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--color-bg-surface);
}
.tool-ribbon button {
  display: grid;
  gap: 6px;
  min-height: 78px;
  padding: 17px 22px;
  text-align: left;
  border: 0;
  border-right: 1px solid var(--color-border-light);
  background: transparent;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.tool-ribbon button:last-child { border-right: 0; }
.tool-ribbon button:hover { background: var(--color-primary-bg); }
.tool-ribbon b { color: var(--color-text); font: 600 15px var(--font-serif); }
.tool-ribbon span { color: var(--color-text-tertiary); font-size: 11px; }

@media (max-width: 1050px) {
  .home-grid { grid-template-columns: 1fr; min-height: 0; }
  .intro { align-self: start; }
  .context-col { align-self: auto; }
  .ctx-card.recent { flex: none; }
}
@media (max-width: 620px) {
  .tool-ribbon { grid-template-columns: 1fr 1fr; }
  .tool-ribbon button:nth-child(2) { border-right: 0; }
  .tool-ribbon button:nth-child(1),
  .tool-ribbon button:nth-child(2) { border-bottom: 1px solid var(--color-border-light); }
}
</style>
