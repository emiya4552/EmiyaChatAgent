// MVU Host 会话编排（ADR-0008c 阶段2b）：把 iframe 宿主 + 卡脚本抽取 + 控制器串起来。
// 上层（chat store / 组件）用法：
//   const sess = new MvuHostSession()
//   await sess.init(persona.card_data)                 // 建沙箱 iframe + 载卡脚本
//   const { stat_data } = await sess.applyTurn(mvu_browser_sync)   // 每回合喂原料拿结算态
//   sess.dispose()                                     // 切会话/卸载时
//
// 取 persona.card_data 交给调用方（decoupled + 可测）。hostFactory 可注入以便 Node 测编排。

import { createIframeHost } from './mvu-host-controller.mjs'
import { extractMvuScripts } from './card-scripts.mjs'

export class MvuHostSession {
  constructor({ hostUrl = '/mvu-host.html', hostFactory = createIframeHost } = {}) {
    this._hostUrl = hostUrl
    this._hostFactory = hostFactory
    this._host = null // { controller, iframe }
    this._loaded = false
  }

  get loaded() { return this._loaded }

  /** 建 iframe + 载卡的 schema/logic/data 脚本。cardData = persona.card_data（原始卡）。
   * 卡没有可跑的 MVU 状态脚本时返回 {ok:false}，不建 iframe。 */
  async init(cardData) {
    const { scripts, skipped } = extractMvuScripts(cardData)
    if (!scripts.length) return { ok: false, reason: 'no MVU state scripts', skipped }
    this._host = this._hostFactory(this._hostUrl)
    await this._host.controller.ready()
    await this._host.controller.loadCard(scripts)
    this._loaded = true
    return { ok: true, scripts: scripts.map((s) => ({ name: s.name, kind: s.kind })), skipped }
  }

  /** 喂一回合原料（message_done.mvu_browser_sync）→ 结算后的 {stat_data, diag}。 */
  async applyTurn(sync) {
    if (!this._loaded) throw new Error('MVU Host 未载入（先 init）')
    return this._host.controller.applyTurn(sync || {})
  }

  dispose() {
    if (this._host) { this._host.controller.dispose(); this._host = null }
    this._loaded = false
  }
}
