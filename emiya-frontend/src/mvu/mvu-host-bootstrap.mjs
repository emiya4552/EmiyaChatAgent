// MVU Host —— 跑在**跨源沙箱 iframe** 里的引导代码（ADR-0008b §1/§3 + ADR-0008c）。
//
// 职责：装 Host 环境（Vendored Stack + Host Shim）→ 装薄 Mvu 层（mvu-runtime.mjs）→
// 载入卡脚本 → 用 postMessage Bridge 与父窗口通信：父发一回合原料（mvu_browser_sync），
// Host 解析+应用+派生，回传结算后的 stat_data。
//
// 安全：iframe 用 `sandbox="allow-scripts"`（不加 allow-same-origin）→ 不透明源，碰不到
// EMIYA 的 session/DOM。卡里抓 window.parent 拿到的是受限对象。
//
// 分层可测：`createBridge` 是纯协议处理器（Node 可测）；`installShims`/`loadCardScripts`/
// `bootMvuHost` 是浏览器专属（CDN + DOM）。

import { createThinMvu } from './mvu-runtime.mjs'

// ── Bridge 协议（父 ↔ Host）──────────────────────────────────────────
// 父→Host： {__mvu:1, type:'load', scripts:[{name,code,kind:'schema'|'logic'|'data'}]}
//          {__mvu:1, id, type:'apply', base_stat, raw_reply, tool_calls, constraints}
// Host→父： {__mvu:1, type:'ready'}
//          {__mvu:1, type:'loaded', ok, error?}
//          {__mvu:1, id, type:'settled', stat_data, diag} | {__mvu:1, id, type:'error', error}
export const MVU_MSG = 1

/**
 * 纯协议处理器：不碰 window/DOM，依赖注入 `post`（回父）与 `loadScripts`（载卡脚本）。
 * 返回 { handleMessage, requestCap }：
 *   - handleMessage(data)：父窗口 message 事件转发进来（load/apply/cap-result）。
 *   - requestCap(cap, args)：Host 侧发起能力请求（ADR-0008d），posts {type:'cap'}，等父回 'cap-result'。
 */
export function createBridge(Mvu, { post, loadScripts }) {
  const capPending = new Map() // cap id -> {resolve, reject}
  let capId = 1

  function requestCap(cap, args) {
    const id = 'c' + (capId++)
    const p = new Promise((resolve, reject) => capPending.set(id, { resolve, reject }))
    post({ __mvu: MVU_MSG, type: 'cap', id, cap, args })
    return p
  }

  async function handleMessage(data) {
    if (!data || data.__mvu !== MVU_MSG) return
    if (data.type === 'cap-result') {
      const p = capPending.get(data.id)
      if (p) { capPending.delete(data.id); data.ok ? p.resolve(data.result) : p.reject(new Error(data.error || 'cap denied')) }
      return
    }
    if (data.type === 'load') {
      try {
        await loadScripts(data.scripts || [])
        post({ __mvu: MVU_MSG, type: 'loaded', ok: true })
      } catch (e) {
        post({ __mvu: MVU_MSG, type: 'loaded', ok: false, error: String((e && e.message) || e) })
      }
      return
    }
    if (data.type === 'apply') {
      try {
        if (data.base_stat) Mvu.setStatData(structuredClone(data.base_stat))
        const r = await Mvu.processTurn({
          raw_reply: data.raw_reply || '',
          tool_calls: data.tool_calls || [],
          double_ai_ops: data.double_ai_ops || [], // double_ai 策略下变量更新的主来源
          constraints: data.constraints || {},
        })
        post({ __mvu: MVU_MSG, id: data.id, type: 'settled', stat_data: r.stat_data, diag: r.diag })
      } catch (e) {
        post({ __mvu: MVU_MSG, id: data.id, type: 'error', error: String((e && e.stack) || e) })
      }
      return
    }
  }

  return { handleMessage, requestCap }
}

// ── 浏览器专属：Host 环境（Vendored Stack + Host Shim）────────────────
// TODO(0008b)：CDN → 自托 Vendored Stack + CSP。spike 阶段先用卡里的 jsdelivr URL。
const CDN = {
  lodash: 'https://testingcf.jsdelivr.net/npm/lodash/+esm',
  jquery: 'https://testingcf.jsdelivr.net/npm/jquery/+esm',
  zod: 'https://testingcf.jsdelivr.net/npm/zod/+esm',
}

export async function installShims(win = window) {
  win._ = (await import(CDN.lodash)).default
  const jq = (await import(CDN.jquery)).default
  win.$ = win.jQuery = jq
  const zmod = await import(CDN.zod)
  win.z = zmod.z || zmod.default || zmod
  win.toastr = new Proxy({}, { get: () => () => {} })

  // 事件总线 + TavernHelper 事件 API
  const bus = new Map()
  win.__mvuBus = bus
  win.eventOn = (n, cb) => { (bus.get(n) || bus.set(n, []).get(n)).push(cb) }
  win.eventMakeLast = win.eventOn
  win.eventRemoveListener = (n, cb) => { const a = bus.get(n); if (a) { const i = a.indexOf(cb); if (i >= 0) a.splice(i, 1) } }
  win.eventEmit = async (n, ...a) => { for (const cb of (bus.get(n) || [])) { try { await cb(...a) } catch (e) { console.warn('[MVU Host] 事件监听抛错(多为卡 UI，无头预期):', e) } } }

  // 载荷关键：真卡把整个 init（含 VARIABLE_UPDATE_ENDED 注册）gate 在 waitGlobalInitialized('Mvu') 后
  win.waitGlobalInitialized = (name, timeoutMs = 3000) => new Promise((resolve, reject) => {
    const t0 = Date.now()
    const check = () => {
      if (win[name] != null) return resolve(win[name])
      if (Date.now() - t0 > timeoutMs) return reject(new Error(name + ' not initialized'))
      setTimeout(check, 20)
    }
    check()
  })

  // SillyTavern flat-context + TavernHelper 变量/楼层 shim（背靠内存楼层，UP 通道见 0008c）
  const st = {
    chat: [{ mes: '', is_user: false, variables: { stat_data: {} } }],
    POPUP: { TYPE: {}, RESULT: {} }, callGenericPopup: async () => null,
    saveChat: async () => {}, getCurrentChatId: () => 'mvu-host', extensionSettings: {}, saveSettingsDebounced: () => {},
  }
  st.getContext = () => st
  win.SillyTavern = st
  win.getLastMessageId = () => 0
  win.getChatMessages = () => st.chat
  win.confirm = win.confirm || (() => false)
}

/** 把一段 ESM 卡脚本源规整成可作为 classic <script> 注入的等价源（纯函数，可测）。
 *
 * 卡脚本本是 ESM 模块（顶层 `import`/`export`），但 Host 按 classic IIFE 注入（sloppy 模式更宽容、
 * 天然作用域隔离）。故须把模块语法降级为等价的普通语句：
 *  - 剥掉**所有静态** import 语句：引擎与库由 Host 全局 shim 提供（`registerMvuSchema`/`z`/`_`/`$`/
 *    `Mvu`/`eventOn`…），无需真去 CDN 拉（MagVarUpdate 引擎整脚本更是早在 classify='bundle' 就 skip）。
 *    **保留动态 `import()`**（UI 脚本按需拉 jquery-ui 等，见 0008d）。
 *  - 剥掉 export：`export const/let/var/function/class/async` 去前缀；`export default …`/`export {…}` 去整句。
 *    让模块顶层导出退化成 IIFE 内普通声明（同 IIFE 内的 `$(()=>registerMvuSchema(Schema))` 闭包照常捕获）。
 *
 * 依据（verify-against-cards，DB 内 3 张 MVU 卡全量实测：伶伶/WuWa/魔法少女）：静态 import 仅出现为
 * MagVarUpdate 引擎与 mvu_zod 的 `registerMvuSchema`；export 仅为 schema 的 `export const Schema`；
 * 无列 0 隐式全局。变换对 logic/data（无 import/export）为 no-op，故可安全套到所有 kind。 */
export function stripModuleSyntax(code) {
  let c = String(code || '')
  // 静态 import 语句（单行形态覆盖卡实况）：`import 'x'` / `import x from 'x'` / `import {…} from 'x'` /
  // `import * as ns from 'x'`。负向前瞻排除动态 `import(`（含 `import (` 空格形态）。
  c = c.replace(/^[ \t]*import\s+(?!\()(?:[^;\n(]*?\s+from\s+)?['"][^'"]+['"][ \t]*;?[ \t]*$/gm, '')
  // export：default / 具名导出整句 / 声明前缀
  c = c.replace(/^[ \t]*export\s+default\s+/gm, '')
  c = c.replace(/^[ \t]*export\s*\{[^}]*\}[ \t]*(?:from\s*['"][^'"]+['"])?[ \t]*;?[ \t]*$/gm, '')
  c = c.replace(/^[ \t]*export\s+(?=(?:const|let|var|function|class|async)\b)/gm, '')
  return c
}

/** 浏览器：把卡脚本注入沙箱。schema/data/logic 都作为 classic IIFE 注入（避免顶层词法互撞）。
 * schema 脚本里的 `registerMvuSchema` 由薄 Mvu 层捕获（win.registerMvuSchema）。*/
/** 载入前对卡脚本源做的有界变换（纯函数，可测）：
 *  - 所有 kind：`stripModuleSyntax` 把 ESM import/export 降级（见上）。
 *  - ui（ADR-0008d）：把 `window.parent`/`window.top`/裸 `parent`/`top` 重写成 `window`，
 *    让卡 UI 挂到本 iframe 而非被沙箱阻断的宿主窗口（卡的 `window.parent.$ || window.$` 变本地挂载）。*/
export function prepareCardCode(sc) {
  let code = stripModuleSyntax((sc && sc.code) || '')
  if (sc && sc.kind === 'ui') {
    code = code
      .replace(/window\s*\.\s*parent/g, 'window')
      .replace(/window\s*\.\s*top/g, 'window')
      .replace(/\bparent\s*\.\s*(\$|window|document|jQuery)/g, 'window.$1')
      .replace(/\btop\s*\.\s*(\$|window|document|jQuery)/g, 'window.$1')
  }
  return code
}

export function makeLoadCardScripts(win = window) {
  return async function loadCardScripts(scripts) {
    for (const sc of scripts) {
      const el = win.document.createElement('script')
      el.textContent = `(function(){\n${prepareCardCode(sc)}\n})();\n//# sourceURL=mvu-card-${sc.name || sc.kind}`
      win.document.body.appendChild(el)
      await new Promise((r) => setTimeout(r, 20))
    }
    await new Promise((r) => setTimeout(r, 60)) // 等 $(async()=>{ await waitGlobalInitialized })  注册完
  }
}

/** ADR-0008d：装 read/dangerous 宿主能力 shim，全部经 Bridge `requestCap` 中介（父侧按
 * `resolveCapability` 放行/拒绝）。local 能力（本回合 stat_data 读写）在 Host 内本地做，不round-trip。 */
export function installCapabilityShims(win, Mvu, requestCap) {
  win.getWorldbook = (book) => requestCap('getWorldbook', { book }) // read
  win.getChatMessages = (range, opts) => requestCap('getChatMessages', { range, opts }) // read（读会话楼层）
  win.generateRaw = (cfg) => requestCap('generateRaw', cfg) // dangerous（默认被拒）
  win.setChatMessages = (msgs, opts) => requestCap('setChatMessages', { msgs, opts }) // dangerous
  win.createChatMessages = (msgs, opts) => requestCap('createChatMessages', { msgs, opts }) // dangerous
  win.deleteChatMessages = (ids, opts) => requestCap('deleteChatMessages', { ids, opts }) // dangerous
  win.getVariables = (args) => (args && args.type === 'global'
    ? requestCap('getVariables', args) // read（全局会话变量）
    : Promise.resolve({ stat_data: Mvu.getStatData() })) // local（本回合 stat_data）
  win.insertOrAssignVariables = (v) => { Object.assign(Mvu.getStatData(), (v && v.stat_data) || v || {}); return Promise.resolve() }
  win.TavernHelper = win.TavernHelper || {}
  win.TavernHelper.getVariables = win.getVariables
  win.TavernHelper.getWorldbook = win.getWorldbook
  win.TavernHelper.getChatMessages = win.getChatMessages
  win.TavernHelper.setChatMessages = win.setChatMessages
  win.TavernHelper.createChatMessages = win.createChatMessages
  win.TavernHelper.deleteChatMessages = win.deleteChatMessages
  win.TavernHelper.generateRaw = win.generateRaw
}

/** 浏览器入口：在沙箱 iframe 文档里调用。装环境→装薄 Mvu→接 Bridge+能力 shim→通知父 ready。 */
export async function bootMvuHost(win = window) {
  await installShims(win)
  const { Mvu, registerMvuSchema } = createThinMvu({ z: win.z, eventEmit: win.eventEmit })
  win.Mvu = Mvu
  win.registerMvuSchema = registerMvuSchema
  const post = (m) => win.parent.postMessage(m, '*')
  const bridge = createBridge(Mvu, { post, loadScripts: makeLoadCardScripts(win) })
  installCapabilityShims(win, Mvu, bridge.requestCap)
  win.addEventListener('message', (ev) => { bridge.handleMessage(ev.data) })
  post({ __mvu: MVU_MSG, type: 'ready' })
}
