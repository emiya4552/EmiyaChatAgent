// MVU Host 父窗口控制器（ADR-0008b §3 / ADR-0008c）——管理沙箱 iframe 生命周期 +
// postMessage Bridge：载卡脚本、每回合把 mvu_browser_sync 喂进 Host、拿回结算 stat_data。
//
// 与 iframe/DOM 解耦：`MvuHostController` 只依赖注入的 `send`（发消息给 Host）；
// 父窗口收到 Host 的消息时调 `onMessage(data)`。correlation-by-id 逻辑 Node 可测。
// 浏览器工厂 `createIframeHost` 负责真正建沙箱 iframe 并接线。

export const MVU_MSG = 1

export class MvuHostController {
  constructor({ send, capabilityHandler } = {}) {
    this._send = send
    this._pending = new Map() // apply id -> {resolve, reject}
    this._nextId = 1
    this._loadWaiters = []
    this._ready = new Promise((res, rej) => { this._readyResolve = res; this._readyReject = rej })
    this._ready.catch(() => {}) // 避免未处理 rejection 噪声（真正的错误由 ready() 的调用方处理）
    // ADR-0008d：处理 Host 主动发起的能力请求（cap）。async (cap, args) => result；throw = 拒绝。
    // 缺省 handler 拒绝一切（安全默认）。上层应注入按 resolveCapability + 后端端点的实现。
    this._capabilityHandler = capabilityHandler || (async (cap) => { throw new Error(`capability denied: ${cap}`) })
  }

  /** 等 Host boot 完成（收到 'ready'）。*/
  ready() { return this._ready }

  /** Host 装配彻底失败（如 bundle 加载出错）：拒掉 ready + 所有挂起，避免上层永远等。*/
  fail(err) {
    const e = err instanceof Error ? err : new Error(String(err))
    this._readyReject(e)
    for (const p of this._pending.values()) p.reject(e)
    this._pending.clear()
    this._loadWaiters.forEach((w) => w.reject(e))
    this._loadWaiters = []
  }

  /** 父窗口 message 事件转发进来。*/
  onMessage(data) {
    if (!data || data.__mvu !== MVU_MSG) return
    switch (data.type) {
      case 'ready':
        this._readyResolve()
        break
      case 'loaded': {
        const w = this._loadWaiters.shift()
        if (w) (data.ok ? w.resolve(true) : w.reject(new Error(data.error || 'load failed')))
        break
      }
      case 'settled': {
        const p = this._pending.get(data.id)
        if (p) { this._pending.delete(data.id); p.resolve({ stat_data: data.stat_data, diag: data.diag }) }
        break
      }
      case 'error': {
        const p = this._pending.get(data.id)
        if (p) { this._pending.delete(data.id); p.reject(new Error(data.error || 'apply failed')) }
        break
      }
      case 'cap': {
        // Host 发起能力请求（ADR-0008d）：交给 handler 裁决，回 cap-result。
        Promise.resolve()
          .then(() => this._capabilityHandler(data.cap, data.args))
          .then((result) => this._send({ __mvu: MVU_MSG, type: 'cap-result', id: data.id, ok: true, result }))
          .catch((e) => this._send({ __mvu: MVU_MSG, type: 'cap-result', id: data.id, ok: false, error: String((e && e.message) || e) }))
        break
      }
    }
  }

  /** 载入卡脚本（schema/data/logic）。resolve 于 Host 回 'loaded'。*/
  async loadCard(scripts) {
    await this._ready
    const p = new Promise((resolve, reject) => this._loadWaiters.push({ resolve, reject }))
    this._send({ __mvu: MVU_MSG, type: 'load', scripts: scripts || [] })
    return p
  }

  /** 喂一回合原料（来自 message_done.mvu_browser_sync）→ resolve 结算后的 {stat_data, diag}。*/
  applyTurn({ base_stat, raw_reply = '', tool_calls = [], double_ai_ops = [], constraints = {} } = {}) {
    const id = String(this._nextId++)
    const p = new Promise((resolve, reject) => this._pending.set(id, { resolve, reject }))
    // double_ai_ops 必须一起传：double_ai 策略下正文无 <UpdateVariable>、tool_calls 空，
    // 变量更新全在 double_ai_ops 里，丢了 Host 就空跑（ADR-0008b/c 断点修复）。
    this._send({ __mvu: MVU_MSG, id, type: 'apply', base_stat, raw_reply, tool_calls, double_ai_ops, constraints })
    return p
  }

  /** 拒掉所有挂起（iframe 销毁时调）。*/
  dispose() {
    for (const p of this._pending.values()) p.reject(new Error('MVU Host disposed'))
    this._pending.clear()
    this._loadWaiters.forEach((w) => w.reject(new Error('MVU Host disposed')))
    this._loadWaiters = []
  }
}

/** 取自包含 Host bundle（虚拟模块，见 vite.config 的 mvuHostBundlePlugin）。
 * 懒加载：只有真正建 iframe 时才拉，Node/Vitest 不注入 factory 就不会触发打包。 */
async function loadHostBundle() {
  const mod = await import('virtual:mvu-host-bundle')
  return mod.default
}

/** 把自包含 bundle 源码内联进一张 srcdoc 文档。
 * 关键：脚本以**内联 <script>** 注入，浏览器不会为它发 fetch → 不透明源下也无 CORS。
 * bundle 里唯一的外部依赖是 jsdelivr 的 `import('https://…')`（跨源 CORS，jsdelivr 回 ACAO:* 放行）。 */
export function buildHostDoc(bundleSrc) {
  // 防御性转义：内联脚本里若含 `</script>` 会提前闭合。Host 源码目前不含，转义仅为兜底。
  const safe = String(bundleSrc).replace(/<\/script>/gi, '<\\/script>')
  // TODO(0008b)：加 <meta http-equiv="Content-Security-Policy"> 锁 connect-src 到自托 Vendored Stack。
  return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>MVU Host</title></head>`
    + `<body><script>${safe}</script></body></html>`
}

/**
 * 浏览器：建一个跨源沙箱 iframe 装 Host，返回接好线的 controller。
 *
 * ADR-0008b 修订：Host 代码经 `srcdoc` 内联注入（自包含 bundle），**不再** `src="/mvu-host.html"`。
 * 原因：`sandbox="allow-scripts"`（无 allow-same-origin）的文档是不透明源（Origin: null），
 * 从它按 CORS 模式 fetch 同源的 module 脚本会被 Vite/生产服务器拦（ERR_FAILED）→ Host 从未 boot。
 * srcdoc 内联脚本无 fetch，opaque 源隔离照样保留，dev/生产都可用。
 *
 * @param _hostUrl 已弃用（srcdoc 内联注入，无需 URL）；保留形参以兼容既有调用/测试签名。
 * @param sandbox 默认 'allow-scripts'（不加 allow-same-origin → 不透明源，碰不到 EMIYA session/DOM）。
 */
export function createIframeHost(_hostUrl, { sandbox = 'allow-scripts', parent = document.body, capabilityHandler } = {}) {
  const iframe = document.createElement('iframe')
  iframe.setAttribute('sandbox', sandbox)
  iframe.style.display = 'none' // 状态阶段无头；UI 阶段（0008d）改可见 + 布局停靠区

  const controller = new MvuHostController({
    send: (m) => iframe.contentWindow && iframe.contentWindow.postMessage(m, '*'),
    capabilityHandler, // ADR-0008d：卡能力请求裁决（缺省全拒）
  })

  const onMsg = (ev) => {
    if (ev.source && ev.source === iframe.contentWindow) controller.onMessage(ev.data)
  }
  window.addEventListener('message', onMsg)

  const origDispose = controller.dispose.bind(controller)
  controller.dispose = () => {
    window.removeEventListener('message', onMsg)
    iframe.remove()
    origDispose()
  }

  parent.appendChild(iframe)

  // 异步拉 bundle → 注入 srcdoc。iframe 载入后 bootMvuHost 会 postMessage 'ready'，
  // controller.ready() 随之 resolve。加载失败则 fail 掉 controller，避免上层永远等。
  loadHostBundle()
    .then((src) => { iframe.srcdoc = buildHostDoc(src) })
    .catch((e) => { console.error('[MVU Host] bundle 加载失败:', e); controller.fail(e) })

  return { controller, iframe }
}
