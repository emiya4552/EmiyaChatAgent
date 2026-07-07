import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Message } from '../types'
import * as chatApi from '../api/chat'
import { useConversationStore } from './conversation'
import { useAuthStore } from './auth'
import { fetchPersonaDetail } from '../api/persona'
import {
  updateMvuState,
  mvuGetWorldbook, mvuGetChatMessages, mvuGenerateRaw,
  mvuCreateChatMessages, mvuSetChatMessages, mvuDeleteChatMessages,
} from '../api/conversation'
import { setMvuStatData } from '../composables/useHtmlIframeRender'
// ADR-0008c 阶段2：浏览器 MVU Host（仅当后端开 MVU_BROWSER_RUNTIME、message_done 带
// mvu_browser_sync 时才懒创建 iframe；flag 关时零开销）。.mjs 无 TS 声明，用 any 承接。
// @ts-ignore
import { MvuHostSession } from '../mvu/mvu-host-session.mjs'
// @ts-ignore
import { extractMvuScripts } from '../mvu/card-scripts.mjs'
// @ts-ignore
import { makeCapabilityHandler } from '../mvu/mvu-capabilities.mjs'

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const isStreaming = ref(false)
  const streamingContent = ref('')
  const error = ref<string | null>(null)
  // MVU 诊断运行时视图（ADR-0003 §3）：每轮 message_done 派生，仅当前对话
  const mvuRuntimeView = ref<import('../types').MvuRuntimeView | null>(null)
  const hasMoreMessages = ref(false)

  let abortController: AbortController | null = null
  let liveAbortController: AbortController | null = null
  let liveAiMsgId: string | null = null
  let _currentPage = 0
  const _pageSize = 200

  // ── ADR-0008c/d：浏览器 MVU Host 会话（懒创建 + 预热 + UI 停靠栏，见 src/mvu/README.md）──
  let mvuSession: any = null
  let mvuSessionConvId: string | null = null
  let mvuInitPromise: Promise<any> | null = null // 建 Host 的在途 promise：并发/重复触发共享同一次构建，避免竞态重建 + 双份 CDN 加载
  let mvuLastTurnKey: string | null = null        // 已处理的 message_done 去重键（两个 onDone 路径会各触发一次同一回合）
  // ADR-0008d：卡 UI 停靠栏。容器由 MvuHostDock.vue 注册；mvuHostActive 决定停靠栏是否显示。
  const mvuHostContainer = ref<HTMLElement | null>(null)
  const mvuHostActive = ref(false) // 当前卡有可渲染 UI（logic/ui 脚本）且容器就绪时为真 → 显示停靠栏
  let _mvuContainerWaiters: Array<(el: HTMLElement | null) => void> = []
  function registerMvuHostContainer(el: HTMLElement | null) {
    mvuHostContainer.value = el
    if (el) { _mvuContainerWaiters.forEach((w) => w(el)); _mvuContainerWaiters = [] }
  }
  // 等停靠栏容器就绪（iframe 建成后不可移动，故须建 Host 前备好容器）。超时 → null（无头兜底）。
  function _waitForMvuContainer(timeoutMs = 4000): Promise<HTMLElement | null> {
    if (mvuHostContainer.value) return Promise.resolve(mvuHostContainer.value)
    return new Promise((resolve) => {
      const w = (el: HTMLElement | null) => resolve(el)
      _mvuContainerWaiters.push(w)
      setTimeout(() => {
        const i = _mvuContainerWaiters.indexOf(w)
        if (i >= 0) { _mvuContainerWaiters.splice(i, 1); resolve(mvuHostContainer.value) }
      }, timeoutMs)
    })
  }
  function disposeMvuSession() {
    if (mvuSession) { try { mvuSession.dispose() } catch { /* ignore */ } mvuSession = null }
    mvuSessionConvId = null
    mvuInitPromise = null
    mvuHostActive.value = false
  }

  // ADR-0008d：给某会话构建能力处理器。read（getWorldbook/getChatMessages）默认放行走后端只读端点；
  // dangerous（generateRaw 卡调 LLM / set/create/deleteChatMessages 卡改会话）仅在该会话 opt-in 时放行。
  function _buildMvuCapabilityHandler(conversationId: string, dangerous: boolean) {
    const cid = conversationId
    const providers = {
      // read
      getWorldbook: (a: any) => mvuGetWorldbook(cid, a?.book),
      getChatMessages: (a: any) => mvuGetChatMessages(cid, String(a?.range ?? '-1')),
      getVariables: async () => ({}), // 全局会话变量：EMIYA 无 → 空对象（卡兜底）
      // dangerous
      generateRaw: (cfg: any) => mvuGenerateRaw(cid, {
        user_input: cfg?.user_input, prompt: cfg?.prompt,
        ordered_prompts: cfg?.ordered_prompts,
        temperature: cfg?.temperature, max_tokens: cfg?.max_tokens,
      }).then((r: any) => r?.text ?? ''),
      setChatMessages: (a: any) => mvuSetChatMessages(cid, (a?.msgs || []).map((m: any) => ({
        message_id: m?.message_id, message: m?.message, data: m?.data,
      }))),
      createChatMessages: (a: any) => {
        const ib = a?.opts?.insert_before
        return mvuCreateChatMessages(cid, (a?.msgs || []).map((m: any) => ({
          role: m?.role, message: m?.message, data: m?.data,
        })), typeof ib === 'number' ? ib : null)
      },
      deleteChatMessages: (a: any) => mvuDeleteChatMessages(cid, (a?.ids || []).map((x: any) => Number(x))).then((r: any) => r?.deleted ?? 0),
    }
    return makeCapabilityHandler({ policy: { read: true, dangerous }, providers })
  }

  // 确保当前对话的 Host 会话就绪。并发/重复调用共享同一 in-flight 构建（去掉双 onDone 造成的双份建 iframe +
  // 双份 jsdelivr CDN 加载的竞态）。非 MVU 卡（无可跑脚本）返回 null 且不建 iframe。
  // ADR-0008d：卡有 UI（logic/ui 脚本）时载 UI 脚本 + 把 iframe 挂进停靠栏可见渲染 + 接能力处理器。
  function ensureMvuSession(conversationId: string): Promise<any> {
    // CARD-0002：账户级 MVU 兼容开关 off → 把 MVU 卡当普通卡，不建 Host 会话、不亮卡 UI 停靠栏。
    if (useAuthStore().user?.mvu_compat_enabled === false) {
      mvuHostActive.value = false
      return Promise.resolve(null)
    }
    if (mvuSession && mvuSessionConvId === conversationId) return Promise.resolve(mvuSession)
    if (mvuInitPromise && mvuSessionConvId === conversationId) return mvuInitPromise
    if (mvuSessionConvId && mvuSessionConvId !== conversationId) disposeMvuSession()
    mvuSessionConvId = conversationId
    const p: Promise<any> = (async () => {
      const conv = useConversationStore().list.find((c) => c.id === conversationId) as any
      const personaId = conv?.persona_id
      if (!personaId) return null
      const detail = await fetchPersonaDetail(personaId) as any
      // 卡有没有可渲染 UI（schema-only 如伶伶 → 无 UI，不亮停靠栏）
      const extracted = extractMvuScripts(detail?.card_data, { includeUi: true })
      const hasUi = (extracted?.scripts || []).some((s: any) => s.kind === 'ui' || s.kind === 'logic')
      const container = hasUi ? await _waitForMvuContainer() : null
      const dangerous = !!(conv?.mvu_capabilities?.dangerous)
      const sess = new MvuHostSession({
        includeUi: true,
        visible: !!container,
        hostContainer: container || undefined,
        capabilityHandler: _buildMvuCapabilityHandler(conversationId, dangerous),
      })
      const r = await sess.init(detail?.card_data)
      if (!r?.ok) { sess.dispose(); return null }
      mvuSession = sess
      mvuHostActive.value = !!container // 有可见 UI 才亮停靠栏
      return sess
    })().catch((e) => { console.warn('[MVU] Host 会话构建失败:', e); return null })
    mvuInitPromise = p
    // 失败（resolve null）时，若仍是当前 in-flight，清掉以允许下一回合重试（成功则 mvuSession 已 set）
    void p.then((s) => { if (!s && mvuInitPromise === p) mvuInitPromise = null })
    return p
  }

  // 收到 message_done.mvu_browser_sync：确保 Host 就绪 → applyTurn → 用浏览器结算的
  // stat_data 覆盖对话状态变量展示（替代后端 data.variables）。全程 try/catch，失败不影响聊天。
  // turnKey（message_id）去重：主 SSE 路径与 live 广播路径会各触发一次同一回合，只处理一次。
  async function handleMvuBrowserSync(conversationId: string, sync: any, turnKey?: string) {
    if (turnKey) {
      if (turnKey === mvuLastTurnKey) return // 同一回合已处理（去重发生在任何 await 之前，天然原子）
      mvuLastTurnKey = turnKey
    }
    const convStore = useConversationStore()
    try {
      const sess = await ensureMvuSession(conversationId)
      if (!sess) return
      const { stat_data } = await sess.applyTurn(sync)
      const idx = convStore.list.findIndex((c) => c.id === conversationId)
      if (idx !== -1) {
        const prev = (convStore.list[idx] as any).variables || {}
        convStore.list[idx] = { ...convStore.list[idx], variables: { ...prev, stat_data } }
      }
      // ADR-0008d：把浏览器结算的（含派生的）stat_data 喂给状态栏 HTML 显示环境
      setMvuStatData(stat_data)
      // ADR-0008c UP 通道：把浏览器结算的 stat_data 回传后端持久化（含派生字段，比后端版更全）。
      // fire-and-forget，失败不影响聊天；下一轮后端仍会用持久化后的这份作基线。
      updateMvuState(conversationId, stat_data).catch((e) => console.warn('[MVU] UP 回传失败:', e))
    } catch (e) {
      console.warn('[MVU] browser-sync 处理失败:', e)
    }
  }

  async function fetchMessages(conversationId: string) {
    _currentPage = 0
    // 切换对话：清掉上一对话的 MVU 诊断视图（它只随 message_done 派生，无法从历史反推）
    mvuRuntimeView.value = null
    // 切换对话：卸掉上一对话的 MVU Host iframe（下条 mvu_browser_sync 会按需重建）
    disposeMvuSession()
    mvuLastTurnKey = null // 换对话：清回合去重键
    // 开会话：把当前对话已持久化的 stat_data 喂给状态栏 HTML 环境（老消息/开场白也能显示）
    {
      const conv = useConversationStore().list.find((c) => c.id === conversationId) as any
      setMvuStatData(conv?.variables?.stat_data || {})
    }
    // 预热：开会话时就后台构建 Host（拉 jsdelivr CDN 依赖 ~数秒），把首回合的构建成本挪到"读历史/打字"
    // 阶段，等用户发消息拿到 mvu_browser_sync 时 applyTurn 已可瞬时结算。非 MVU 卡不建 iframe（init 返回
    // ok:false）。best-effort，失败不影响聊天。
    void ensureMvuSession(conversationId)
    const msgs = await chatApi.fetchMessages(conversationId, _pageSize, 0)
    // 后端按时间倒序，前端需要正序展示
    messages.value = msgs.reverse()
    hasMoreMessages.value = msgs.length >= _pageSize
  }

  async function loadEarlierMessages(conversationId: string) {
    _currentPage++
    const offset = _currentPage * _pageSize
    const older = await chatApi.fetchMessages(conversationId, _pageSize, offset)
    if (older.length === 0) {
      hasMoreMessages.value = false
      return
    }
    // 旧消息插入到列表开头（保持正序）
    messages.value = [...older.reverse(), ...messages.value]
    hasMoreMessages.value = older.length >= _pageSize
  }

  function sendMessage(conversationId: string, content: string, replyLength: string = 'medium') {
    error.value = null
    isStreaming.value = true
    streamingContent.value = ''

    const tempId = 'temp-' + Date.now()
    messages.value.push({
      id: tempId,
      conversation_id: conversationId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    })

    const aiTempId = 'ai-temp-' + Date.now()
    messages.value.push({
      id: aiTempId,
      conversation_id: conversationId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
    })

    const convStore = useConversationStore()

    abortController = chatApi.sendMessage(conversationId, content, replyLength, {
      onToken(token) {
        streamingContent.value += token
        const aiMsg = messages.value.find((m) => m.id === aiTempId)
        if (aiMsg) {
          aiMsg.content = streamingContent.value
        }
      },
      onDone(data) {
        isStreaming.value = false
        streamingContent.value = ''
        abortController = null
        // 用后端返回的真 Message.id 替换 aiTempId；用 final_content 覆盖流式累积版
        // （content=prompt 真相版）；final_display_content 是显示版（ADR-0003 双管线），
        // MessageBubble 优先渲染它，实现流式期间未清洗版 → message_done 后美化版的静默替换。
        const aiMsg = messages.value.find((m) => m.id === aiTempId)
        if (aiMsg) {
          if (data?.message_id) aiMsg.id = data.message_id
          if (typeof data?.final_content === 'string' && data.final_content.length > 0) {
            aiMsg.content = data.final_content
          }
          if (typeof data?.final_display_content === 'string') {
            aiMsg.display_content = data.final_display_content
          }
        }
        if (data?.mvu_runtime_view) {
          mvuRuntimeView.value = data.mvu_runtime_view as import('../types').MvuRuntimeView
        }
        // ADR-0019：情绪随 message_done 到达（emoji 在回合结束时更新，替代旧的回复前 emotion SSE）
        if (data?.emotion) {
          convStore.setMood(data.emotion, data.emotion_intensity ?? 5)
        }
        if (data?.new_memories) {
          convStore.setNewMemoriesCount(data.new_memories)
        }
        // 好感度更新（message_done 中携带）
        if (data?.affinity_score !== undefined && convStore.currentRelationship) {
          convStore.currentRelationship.affinity_score = data.affinity_score
        }
        // MVU v0：把后端写回后的最新 variables 同步到 store，
        // 让 ConfigPanel「对话状态变量」实时刷新（详见 ADR-0010）
        if (data?.variables !== undefined) {
          const idx = convStore.list.findIndex(c => c.id === conversationId)
          if (idx !== -1) {
            convStore.list[idx] = { ...convStore.list[idx], variables: data.variables || {} }
          }
          // ADR-0008d：后端版 stat_data 先喂给状态栏 HTML（浏览器 Host 结算后会再覆盖成含派生的版本）
          setMvuStatData((data.variables as any)?.stat_data || {})
        }
        // ADR-0008c 阶段2：后端开了 MVU_BROWSER_RUNTIME 时，用浏览器 MVU Host 结算状态（覆盖上面的 variables）
        if (data?.mvu_browser_sync) {
          void handleMvuBrowserSync(conversationId, data.mvu_browser_sync, data.message_id)
        }
      },
      onError(err, partialMessageId) {
        error.value = err
        isStreaming.value = false
        abortController = null
        // 中断时如有 partial_message_id（已落库的不完整消息），替换 aiTempId 并补 [流式中断]
        if (partialMessageId) {
          const aiMsg = messages.value.find((m) => m.id === aiTempId)
          if (aiMsg) {
            aiMsg.id = partialMessageId
            aiMsg.content = (aiMsg.content || '') + '[流式中断]'
          }
        }
      },
      onMemoryRecall(memories) {
        convStore.setRecalledMemories(memories)
      },
      onRelationshipChange(data) {
        convStore.setRelationshipChange(data)
      },
      onMilestone(data) {
        convStore.setMilestone(data)
      },
      onProfileReminder(data) {
        convStore.setProfileReminder(data)
      },
      onAffinityUpdate(data) {
        convStore.setAffinityUpdate(data)
      },
      onWorldInfoActivated(data) {
        convStore.setActivatedWorldInfo(data.entries)
      },
    })
  }

  function stopGeneration() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    isStreaming.value = false
  }

  function clearMessages() {
    messages.value = []
    streamingContent.value = ''
    isStreaming.value = false
  }

  function startLiveWatch(conversationId: string) {
    stopLiveWatch()
    const convStore = useConversationStore()
    liveAbortController = new AbortController()

    chatApi.watchLive(conversationId, liveAbortController.signal, {
      onToken(token) {
        // 如果用户自己正在发消息，sendMessage 已在处理流式输出，此处的 live
        // 事件来自 Redis PubSub 广播的同一回复——跳过，避免创建重复消息。
        if (abortController) return

        if (!liveAiMsgId) {
          liveAiMsgId = 'live-' + Date.now()
          messages.value.push({
            id: liveAiMsgId,
            conversation_id: conversationId,
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString(),
          })
        }
        isStreaming.value = true
        streamingContent.value += token
        const aiMsg = messages.value.find((m) => m.id === liveAiMsgId)
        if (aiMsg) aiMsg.content = streamingContent.value
      },
      onDone(data) {
        // 如果用户自己正在发消息，不覆盖 state
        if (abortController) return
        isStreaming.value = false
        streamingContent.value = ''
        // 用真 id 替换 liveAiMsgId 消息；final_content=prompt 真相版，
        // final_display_content=显示版（ADR-0003 双管线，MessageBubble 优先渲染）
        if (liveAiMsgId) {
          const aiMsg = messages.value.find((m) => m.id === liveAiMsgId)
          if (aiMsg) {
            if (data?.message_id) aiMsg.id = data.message_id
            if (typeof data?.final_content === 'string' && data.final_content.length > 0) {
              aiMsg.content = data.final_content
            }
            if (typeof data?.final_display_content === 'string') {
              aiMsg.display_content = data.final_display_content
            }
          }
        }
        if (data?.mvu_runtime_view) {
          mvuRuntimeView.value = data.mvu_runtime_view as import('../types').MvuRuntimeView
        }
        // ADR-0008c 阶段2：浏览器 MVU Host 结算（同 sendMessage 路径）
        if (data?.mvu_browser_sync) {
          void handleMvuBrowserSync(conversationId, data.mvu_browser_sync, data.message_id)
        }
        // ADR-0019：情绪随 message_done 到达
        if (data?.emotion) {
          convStore.setMood(data.emotion, data.emotion_intensity ?? 5)
        }
        liveAiMsgId = null
      },
      onMemoryRecall(memories) {
        convStore.setRecalledMemories(memories)
      },
      onError() {
        if (abortController) return
        isStreaming.value = false
        liveAiMsgId = null
      },
    })
  }

  function stopLiveWatch() {
    liveAiMsgId = null
    isStreaming.value = false
    streamingContent.value = ''
    if (liveAbortController) {
      liveAbortController.abort()
      liveAbortController = null
    }
  }

  return {
    messages,
    isStreaming,
    streamingContent,
    error,
    mvuRuntimeView,
    hasMoreMessages,
    // ADR-0008d：卡 UI 停靠栏（MvuHostDock.vue 注册容器 / 据 mvuHostActive 显示）
    mvuHostActive,
    registerMvuHostContainer,
    fetchMessages,
    loadEarlierMessages,
    sendMessage,
    stopGeneration,
    clearMessages,
    startLiveWatch,
    stopLiveWatch,
  }
})
