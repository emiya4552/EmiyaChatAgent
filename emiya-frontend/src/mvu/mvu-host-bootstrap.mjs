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
import { mvuLog } from './mvu-log.mjs'
import { installTavernHelperApi } from './th-api.mjs'

const _hlog = mvuLog.scope('Host')

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
  const _blog = _hlog.scope('bridge')
  const capPending = new Map() // cap id -> {resolve, reject}
  let capId = 1

  function requestCap(cap, args) {
    const id = 'c' + (capId++)
    _blog.debug('能力请求 →', cap, args ? Object.keys(args) : [])
    const p = new Promise((resolve, reject) => capPending.set(id, { resolve, reject }))
    post({ __mvu: MVU_MSG, type: 'cap', id, cap, args })
    return p
  }

  async function handleMessage(data) {
    if (!data || data.__mvu !== MVU_MSG) return
    if (data.type === 'cap-result') {
      const p = capPending.get(data.id)
      if (p) {
        capPending.delete(data.id)
        _blog.debug('能力结果 ←', data.id, data.ok ? 'allow' : 'deny/err:' + (data.error || ''))
        data.ok ? p.resolve(data.result) : p.reject(new Error(data.error || 'cap denied'))
      }
      return
    }
    if (data.type === 'load') {
      try {
        await loadScripts(data.scripts || [])
        _blog.info('卡脚本载入成功')
        post({ __mvu: MVU_MSG, type: 'loaded', ok: true })
      } catch (e) {
        _blog.error('卡脚本载入失败:', e)
        post({ __mvu: MVU_MSG, type: 'loaded', ok: false, error: String((e && e.message) || e) })
      }
      return
    }
    if (data.type === 'apply') {
      try {
        if (data.base_stat) Mvu.setStatData(structuredClone(data.base_stat))
        _blog.info('applyTurn 入: raw_reply=', (data.raw_reply || '').length, '字',
          'tool_calls=', (data.tool_calls || []).length, 'double_ai_ops=', (data.double_ai_ops || []).length)
        const r = await Mvu.processTurn({
          raw_reply: data.raw_reply || '',
          tool_calls: data.tool_calls || [],
          double_ai_ops: data.double_ai_ops || [], // double_ai 策略下变量更新的主来源
          constraints: data.constraints || {},
        })
        _blog.info('applyTurn 出: applied=', (r.diag && r.diag.applied),
          'stat_data 顶层键=', Object.keys((r.stat_data && r.stat_data.stat_data) || r.stat_data || {}))
        post({ __mvu: MVU_MSG, id: data.id, type: 'settled', stat_data: r.stat_data, diag: r.diag })
      } catch (e) {
        _blog.error('applyTurn 抛错:', e)
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
  // jQuery UI 完整 dist（classic 全量包，含 mouse+draggable widget）。ESM 形态接不上
  // $.ui.mouse，故用 classic <script> 在全局 jQuery 就位后装（ADR-0008d 悬浮球/飞讯依赖）。
  jqueryUi: 'https://testingcf.jsdelivr.net/npm/jquery-ui-dist@1.13.2/jquery-ui.min.js',
  // Font Awesome：卡 UI 满屏用 fa-solid 图标（悬浮球 fa-comment-dots、控制台按钮等）。
  // 缺它则图标全不可见 → 悬浮球看不到也点不到 → 飞讯打不开。
  fontAwesome: 'https://testingcf.jsdelivr.net/npm/@fortawesome/fontawesome-free@6/css/all.min.css',
}

/** 在 iframe 内以 classic <script src> 装外部脚本并等其就绪；失败不阻断（降级）。 */
function _loadClassicScript(win, src, label) {
  return new Promise((resolve) => {
    const el = win.document.createElement('script')
    el.src = src
    el.onload = () => { _hlog.debug('classic 脚本已装:', label); resolve(true) }
    el.onerror = () => { _hlog.warn(`${label} 加载失败，相关 UI 降级:`, src); resolve(false) }
    ;(win.document.head || win.document.documentElement).appendChild(el)
  })
}

/** 在 iframe 内装外部样式表（如 Font Awesome）并等其就绪；失败不阻断（图标降级为不可见）。 */
function _loadStylesheet(win, href, label) {
  return new Promise((resolve) => {
    const el = win.document.createElement('link')
    el.rel = 'stylesheet'
    el.href = href
    el.onload = () => { _hlog.debug('样式表已装:', label); resolve(true) }
    el.onerror = () => { _hlog.warn(`${label} 加载失败，相关图标不可见:`, href); resolve(false) }
    ;(win.document.head || win.document.documentElement).appendChild(el)
  })
}

/** 沙箱（allow-scripts 无 allow-same-origin）下 localStorage/sessionStorage 访问即抛
 * SecurityError（卡 UI 常存拖拽位置/折叠态等偏好，如 jQuery UI draggable 的 stop 回调）。
 * 用内存版兜底：**不跨会话持久化**，但不再抛，卡 UI 正常运行。 */
function _installStorageShim(win) {
  const _mk = () => {
    const m = new Map()
    return {
      getItem: (k) => (m.has(String(k)) ? m.get(String(k)) : null),
      setItem: (k, v) => { m.set(String(k), String(v)) },
      removeItem: (k) => { m.delete(String(k)) },
      clear: () => m.clear(),
      key: (i) => Array.from(m.keys())[i] ?? null,
      get length() { return m.size },
    }
  }
  for (const name of ['localStorage', 'sessionStorage']) {
    try {
      Object.defineProperty(win, name, { value: _mk(), configurable: true })
    } catch (e) {
      _hlog.warn(`${name} shim 安装失败（卡若用 storage 可能抛）:`, e)
    }
  }
}

export async function installShims(win = window) {
  _hlog.info('装载 Host 环境（Vendored Stack + Shim）…')
  win._ = (await import(CDN.lodash)).default
  const jq = (await import(CDN.jquery)).default
  win.$ = win.jQuery = jq
  // 全局 jQuery 就位后再装 classic jQuery UI —— 让 $.ui.mouse + $.fn.draggable 挂到本 jQuery，
  // 卡的动态 import(jquery-ui) 与 $(x).draggable() 即命中；装不上则 draggable 类 UI 优雅降级。
  const [uiOk, faOk] = await Promise.all([
    _loadClassicScript(win, CDN.jqueryUi, 'jQuery UI'),
    _loadStylesheet(win, CDN.fontAwesome, 'Font Awesome'),
  ])
  _hlog.info('Vendored Stack:',
    'lodash✓ jQuery✓ zod… jQueryUI' + (uiOk ? '✓' : '✗（draggable 类 UI 降级）')
    + ' FontAwesome' + (faOk ? '✓' : '✗（图标不可见）'),
    '| $.fn.draggable=', typeof (jq.fn && jq.fn.draggable), '$.ui.mouse=', !!(jq.ui && jq.ui.mouse))
  const zmod = await import(CDN.zod)
  win.z = zmod.z || zmod.default || zmod
  win.toastr = new Proxy({}, { get: () => () => {} })
  _installStorageShim(win)  // 沙箱下 localStorage 抛错兜底（卡 UI 拖拽位置等偏好）

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

  // 卡 UI 常调的只读 worldbook / 变量查询宿主 API（无头安全降级：空集 / 当前 stat_data）。
  // 卡自定义的同名函数在其 IIFE 内会就地遮蔽这些全局，故加这些只在卡未定义时兜底、不误伤。
  win.getCharWorldbookNames = () => []
  win.getGlobalWorldbookNames = () => []
  win.getChatWorldbookName = () => null
  win.getModelList = () => []
  win.getAllVariables = () => ({
    stat_data: (win.Mvu && win.Mvu.getStatData && win.Mvu.getStatData()) || {},
  })

  // 卡 UI 常调的 TavernHelper 写/生成/提示注入类 API —— 无头安全降级为 no-op/空。
  // **完整补 TavernHelper 表面**（而非按单卡补），让卡 UI init 不因缺某函数中途抛错静默 bail
  // （如飞讯 init 调 injectPrompts 缺失 → 悬浮球建不出来）。真正的写效果不落地是可接受的降级。
  win.deleteVariable = (key) => {
    try { const sd = win.Mvu?.getStatData?.() || {}; if (key != null && key in sd) delete sd[key] } catch (e) {}
    return Promise.resolve()
  }
  win.getButtonEvent = () => null
  win.updateWorldbookWith = () => Promise.resolve()
  win.injectPrompts = () => Promise.resolve()
  win.uninjectPrompts = () => Promise.resolve()
  win.stopAllGeneration = () => Promise.resolve()
  win.stopGenerationById = () => Promise.resolve()
  win.appendInexistentScriptButtons = () => {}
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
  const log = _hlog.scope('script')
  return async function loadCardScripts(scripts) {
    log.info('载入卡脚本', scripts.length, '个:',
      scripts.map((s) => `${s.name || '?'}(${s.kind})`).join(', '))
    for (const sc of scripts) {
      const name = sc.name || sc.kind
      // 关键：逐条在注入**前**打点。卡脚本若有语法错（走 window.onerror，try/catch 抓不到），
      // 紧挨着这条 debug 的 SyntaxError 即指认是这个脚本 → 直接定位 prepareCardCode 改坏了谁。
      log.debug('→ 注入', name, 'kind=', sc.kind, 'len=', ((sc && sc.code) || '').length)
      const el = win.document.createElement('script')
      el.textContent = `(function(){\n${prepareCardCode(sc)}\n})();\n//# sourceURL=mvu-card-${name}`
      try {
        win.document.body.appendChild(el)
      } catch (e) {
        log.error('脚本注入同步抛错', name, e)
      }
      await new Promise((r) => setTimeout(r, 20))
    }
    log.info('卡脚本载入完成')
    await new Promise((r) => setTimeout(r, 60)) // 等 $(async()=>{ await waitGlobalInitialized })  注册完
  }
}

/** ADR-0008d 卡驱动"写入对话"（第 4 类）：有些卡（角色创建自动开场、选项式推进）靠**戳 ST 的
 * 发送 DOM**（`#send_textarea` + `#send_but`/`#send_form`）把消息发出去。沙箱里没有 ST DOM →
 * 卡报 "SillyTavern UI not found" → 退回剪贴板让用户手动粘贴。这里放一套**隐藏的等价发送 DOM**：
 * 卡设值 + 点发送按钮 / 提交表单 / 在输入框回车时，统一转成 `sendMessage` 能力（dangerous，默认拒、
 * 需对话开启）→ 父窗口走 EMIYA 真实聊天发送。元素 off-screen 且非 position:fixed，故不会被
 * startUiOverlayReporter 当作卡 UI 矩形上报。*/
function _installChatSendDom(win, requestCap) {
  const doc = win.document
  if (!doc || doc.getElementById('send_textarea')) return
  const fire = () => {
    const ta = doc.getElementById('send_textarea')
    const text = (ta && ta.value) || ''
    if (!String(text).trim()) return
    if (ta) ta.value = ''
    Promise.resolve(requestCap('sendMessage', { text }))
      .catch((e) => _hlog.warn('卡发消息被拒/失败（对话需开启 dangerous 能力）:', (e && e.message) || e))
  }
  const form = doc.createElement('form')
  form.id = 'send_form'
  form.setAttribute('style', 'position:absolute;left:-9999px;top:0;width:1px;height:1px;overflow:hidden;opacity:0')
  const ta = doc.createElement('textarea')
  ta.id = 'send_textarea'
  const btn = doc.createElement('div') // ST 的 #send_but 是 <div>，不是 <button>
  btn.id = 'send_but'
  form.appendChild(ta)
  form.appendChild(btn)
  ;(doc.body || doc.documentElement).appendChild(form)
  btn.addEventListener('click', (e) => { e.preventDefault(); fire() })
  form.addEventListener('submit', (e) => { e.preventDefault(); fire() })
  ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); fire() } })
  _hlog.debug('已装 ST 发送 DOM 兼容（#send_textarea/#send_but）→ sendMessage 能力')
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
  win.TavernHelper.getContext = () => win.SillyTavern
  // 完整补面：安装期装的只读/写类全局 shim 也镜像到 TavernHelper.*（有些卡走命名空间调用）。
  for (const k of [
    'getCharWorldbookNames', 'getGlobalWorldbookNames', 'getChatWorldbookName', 'getModelList',
    'getAllVariables', 'insertOrAssignVariables', 'deleteVariable', 'getButtonEvent',
    'updateWorldbookWith', 'injectPrompts', 'uninjectPrompts', 'stopAllGeneration',
    'stopGenerationById', 'appendInexistentScriptButtons', 'getLastMessageId',
  ]) {
    if (typeof win[k] === 'function') win.TavernHelper[k] = win[k]
  }
  // 注：卡驱动"写入对话"的假 ST 发送 DOM **不在此无条件装**——仅在对话开启 dangerous 时装（见
  // bootMvuHost 的 load.dangerous 门控）。否则会遮蔽卡自身"UI not found→剪贴板"降级，反而更糟。
}

/** ADR-0008d 覆盖式布局：Host 铺满聊天区（透明、默认 pointer-events:none），卡 UI 的
 * `position:fixed` 浮层（悬浮球/面板/终端）就能像在 ST 整窗一样铺开、拖曳。为让"卡 UI 上可点、
 * 空白处穿透给聊天"，Host 把**卡 UI 元素的矩形**上报父窗口；父窗口据此在鼠标落到卡 UI 上时才把
 * iframe 切成可点（见 MvuHostDock.vue）。pe:auto 时鼠标事件进 iframe、父窗口收不到，故此处再把
 * 指针位置回传，父窗口才知道何时鼠标离开卡 UI、该切回穿透。 */
function startUiOverlayReporter(win, post) {
  const collectRects = () => {
    const out = []
    const body = win.document.body
    for (const el of (body ? body.children : [])) {
      let cs
      try { cs = win.getComputedStyle(el) } catch { continue }
      if (cs.position !== 'fixed' || cs.display === 'none' || cs.visibility === 'hidden') continue
      if (cs.pointerEvents === 'none' || Number(cs.opacity) === 0) continue
      const r = el.getBoundingClientRect()
      if (r.width < 2 || r.height < 2) continue
      out.push({ x: r.left, y: r.top, w: r.width, h: r.height })
    }
    return out
  }
  let last = ''
  const report = () => {
    const rects = collectRects()
    const sig = JSON.stringify(rects)
    if (sig !== last) { last = sig; post({ __mvu: MVU_MSG, type: 'ui-rects', rects }) }
  }
  let scheduled = false
  const schedule = () => {
    if (scheduled) return
    scheduled = true
    win.requestAnimationFrame(() => { scheduled = false; report() })
  }
  try {
    new win.MutationObserver(schedule).observe(win.document.documentElement, {
      childList: true, subtree: true, attributes: true,
      attributeFilter: ['style', 'class', 'hidden'],
    })
  } catch (e) { _hlog.warn('ui-rects observer 失败:', e) }
  win.setInterval(schedule, 400) // 兜底：拖拽 transform 变化 MutationObserver 常漏
  win.addEventListener('pointermove',
    (e) => post({ __mvu: MVU_MSG, type: 'host-pointer', x: e.clientX, y: e.clientY }), true)
  schedule()
}

/** 浏览器入口：在沙箱 iframe 文档里调用。装环境→装薄 Mvu→接 Bridge+能力 shim→通知父 ready。 */
export async function bootMvuHost(win = window) {
  _hlog.info('bootMvuHost 开始')
  try {
    await installShims(win)
    const { Mvu, registerMvuSchema } = createThinMvu({ z: win.z, eventEmit: win.eventEmit })
    win.Mvu = Mvu
    win.registerMvuSchema = registerMvuSchema
    const post = (m) => win.parent.postMessage(m, '*')
    const bridge = createBridge(Mvu, { post, loadScripts: makeLoadCardScripts(win) })
    installCapabilityShims(win, Mvu, bridge.requestCap)
    // 照酒馆助手 @types 补全整个 TavernHelper API 表面（137 fn）——只填 installShims/Cap 未装的空缺，
    // 让任何卡都不会撞"函数未定义"（@types-驱动兼容层，见 th-api.mjs / direction-and-progress.md）。
    installTavernHelperApi(win, { requestCap: bridge.requestCap })
    win.addEventListener('message', (ev) => { bridge.handleMessage(ev.data) })
    // 卡驱动"写入对话"（第 4 类）：**仅当该对话开启 dangerous** 时装假 ST 发送 DOM（随 load 消息带
    // 的 dangerous 标志）。dangerous 关时不装 → 卡的 `if(!ta||!btn)` 检查失败 → 保留卡自身
    // "SillyTavern UI not found → 复制到剪贴板" 降级（不回归）。_installChatSendDom 自带重复装守卫。
    win.addEventListener('message', (ev) => {
      const d = ev.data
      if (d && d.__mvu === MVU_MSG && d.type === 'load' && d.dangerous) _installChatSendDom(win, bridge.requestCap)
    })
    // 兜底：卡 UI 的未捕获错误统一挂 [MVU] 前缀，便于在 Console 里归因到 MVU Host。
    win.addEventListener('error', (e) => _hlog.warn('Host 未捕获错误:', e.message, '@', e.filename + ':' + e.lineno))
    startUiOverlayReporter(win, post) // 覆盖式布局:上报卡 UI 矩形 + 指针，供父窗口做穿透编排
    post({ __mvu: MVU_MSG, type: 'ready' })
    _hlog.info('Host ready，已通知父窗口')
  } catch (e) {
    _hlog.error('bootMvuHost 失败:', e)
    throw e
  }
}
