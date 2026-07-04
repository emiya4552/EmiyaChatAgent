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
    this._ready = new Promise((res) => { this._readyResolve = res })
    // ADR-0008d：处理 Host 主动发起的能力请求（cap）。async (cap, args) => result；throw = 拒绝。
    // 缺省 handler 拒绝一切（安全默认）。上层应注入按 resolveCapability + 后端端点的实现。
    this._capabilityHandler = capabilityHandler || (async (cap) => { throw new Error(`capability denied: ${cap}`) })
  }

  /** 等 Host boot 完成（收到 'ready'）。*/
  ready() { return this._ready }

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

/**
 * 浏览器：建一个跨源沙箱 iframe 装 Host，返回接好线的 controller。
 * @param hostUrl 指向 Host 页（跑 bootMvuHost 的那张 html）。
 * @param sandbox 默认 'allow-scripts'（不加 allow-same-origin → 不透明源，碰不到 EMIYA session/DOM）。
 * TODO(0008b)：hostUrl 应指向自托 Vendored Stack 的页；CSP 锁 script-src/connect-src。
 */
export function createIframeHost(hostUrl, { sandbox = 'allow-scripts', parent = document.body, capabilityHandler } = {}) {
  const iframe = document.createElement('iframe')
  iframe.setAttribute('sandbox', sandbox)
  iframe.style.display = 'none' // 状态阶段无头；UI 阶段（0008d）改可见 + 布局停靠区
  iframe.src = hostUrl

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
  return { controller, iframe }
}
