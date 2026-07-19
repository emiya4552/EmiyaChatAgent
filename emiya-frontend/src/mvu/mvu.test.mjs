// ADR-0008b/c 前端 MVU Host 单元测试（Vitest）。锁定各模块核心逻辑。
import { describe, it, expect } from 'vitest'
import {
  parseUpdateOps, toolCallsToOps, validateOps, applyOps, createThinMvu,
} from './mvu-runtime.mjs'
import { classifyMvuScript, extractMvuScripts, cardHasMvuStateScripts } from './card-scripts.mjs'
import { createBridge, MVU_MSG, prepareCardCode, stripModuleSyntax } from './mvu-host-bootstrap.mjs'
import { MvuHostController } from './mvu-host-controller.mjs'
import { MvuHostSession } from './mvu-host-session.mjs'
import { classifyCapability, resolveCapability, makeCapabilityHandler } from './mvu-capabilities.mjs'
import { installTavernHelperApi } from './th-api.mjs'

const tick = () => new Promise((r) => setTimeout(r))

function mvuWithDerive() {
  const bus = new Map()
  const eventEmit = async (n, ...a) => { for (const cb of (bus.get(n) || [])) await cb(...a) }
  const { Mvu, events } = createThinMvu({ eventEmit })
  bus.set(events.VARIABLE_UPDATE_ENDED, [(vars) => {
    const d = vars.stat_data
    for (const k of Object.keys(d.角色 || {})) {
      d.角色[k]._态度 = (d.角色[k].好感 >= 80) ? '亲近' : '普通'
    }
  }])
  return { Mvu, events }
}

describe('mvu-runtime: 解析/校验/应用', () => {
  it('parseUpdateOps: <JSONPatch> + 裸数组剥 Analysis', () => {
    expect(parseUpdateOps('<UpdateVariable><JSONPatch>[{"op":"set","path":"/a","value":1}]</JSONPatch></UpdateVariable>'))
      .toEqual([{ op: 'set', path: '/a', value: 1 }])
    expect(parseUpdateOps('<UpdateVariable><Analysis>[无关]</Analysis>[{"op":"set","path":"/b","value":2}]</UpdateVariable>'))
      .toEqual([{ op: 'set', path: '/b', value: 2 }])
  })

  it('toolCallsToOps: 抽 update_variables.patch', () => {
    expect(toolCallsToOps([
      { function: { name: 'update_variables', arguments: JSON.stringify({ patch: [{ op: 'set', path: '/a', value: 1 }] }) } },
      { function: { name: 'other', arguments: '{}' } },
    ])).toEqual([{ op: 'set', path: '/a', value: 1 }])
  })

  it('validateOps: _ 只读丢弃 / coerce / clamp / enum-drop', () => {
    const r1 = validateOps({}, [{ op: 'replace', path: '/x/_ro', value: 1 }, { op: 'replace', path: '/x/y', value: 1 }])
    expect(r1.accepted.length).toBe(1)
    expect(r1.diag.dropped.length).toBe(1)
    expect(validateOps({ 好感: 40 }, [{ op: 'replace', path: '/好感', value: '88' }]).accepted[0].value).toBe(88)
    const clamp = validateOps({ 好感: 40 }, [{ op: 'replace', path: '/好感', value: 150 }], { 好感: { min: 0, max: 100 } })
    expect(clamp.accepted[0].value).toBe(100)
    const en = validateOps({ e: 'a' }, [{ op: 'replace', path: '/e', value: 'z' }], { e: { enum: ['a', 'b'] } })
    expect(en.accepted.length).toBe(0)
  })

  it('applyOps: 嵌套 set/delta/remove', () => {
    const s = {}
    applyOps(s, [{ op: 'set', path: '/a/b', value: 5 }])
    applyOps(s, [{ op: 'delta', path: '/a/b', value: 3 }])
    expect(s.a.b).toBe(8)
    applyOps(s, [{ op: 'remove', path: '/a/b' }])
    expect(s.a.b).toBeUndefined()
  })

  it('processTurn: inline + tool 合并 → 应用 → 派生', async () => {
    const { Mvu } = mvuWithDerive()
    Mvu.setStatData({ 角色: { 甲: { 好感: 40 } }, 物品: 0 })
    const r = await Mvu.processTurn({
      raw_reply: '<UpdateVariable>[{"op":"replace","path":"/角色/甲/好感","value":88}]</UpdateVariable>',
      tool_calls: [{ function: { name: 'update_variables', arguments: JSON.stringify({ patch: [{ op: 'replace', path: '/物品', value: 5 }] }) } }],
    })
    expect(r.stat_data.角色.甲.好感).toBe(88)
    expect(r.stat_data.物品).toBe(5)
    expect(r.stat_data.角色.甲._态度).toBe('亲近') // 派生
  })

  it('processTurn: AI 篡改 _ 字段被丢，派生仍算真值', async () => {
    const { Mvu } = mvuWithDerive()
    Mvu.setStatData({ 角色: { 甲: { 好感: 40 } } })
    const r = await Mvu.processTurn({
      raw_reply: '<UpdateVariable>[{"op":"replace","path":"/角色/甲/好感","value":88},{"op":"replace","path":"/角色/甲/_态度","value":"伪造"}]</UpdateVariable>',
    })
    expect(r.diag.dropped.length).toBe(1)
    expect(r.stat_data.角色.甲._态度).toBe('亲近')
  })
})

const FIXTURE_CARD = {
  data: {
    extensions: {
      tavern_helper: {
        scripts: [
          { name: 'MVU', enabled: true, content: "import 'https://x/MagVarUpdate/bundle.js'" },
          { name: '变量结构', enabled: true, content: 'const S = z.object({}); registerMvuSchema(S)' },
          { name: '剧情数据库', enabled: true, content: 'globalThis.WuWaShared = { STORY_MAP: [] }' },
          { name: '剧情逻辑', enabled: true, content: 'function calculateStoryLogic(d){return d} eventOn(Mvu.events.VARIABLE_UPDATE_ENDED, ()=>{})' },
          { name: '飞讯', enabled: true, content: 'generateRaw(); setChatMessages([])' },
          { name: '禁用的', enabled: false, content: 'registerMvuSchema(x)' },
        ],
      },
    },
  },
}

describe('card-scripts: 从 card_data 抽取+分类', () => {
  it('classifyMvuScript', () => {
    expect(classifyMvuScript("import 'https://x/MagVarUpdate/bundle.js'")).toBe('bundle')
    expect(classifyMvuScript('registerMvuSchema(S)')).toBe('schema')
    expect(classifyMvuScript('calculateStoryLogic(d)')).toBe('logic')
    expect(classifyMvuScript('generateRaw()')).toBe('ui')
    expect(classifyMvuScript('const x = 1')).toBe('data')
  })

  it('extractMvuScripts: 载 schema/logic/data，跳 bundle/ui/disabled', () => {
    const { scripts, skipped } = extractMvuScripts(FIXTURE_CARD)
    expect(scripts.map((s) => s.kind).sort()).toEqual(['data', 'logic', 'schema'])
    expect(skipped.some((s) => s.name === 'MVU')).toBe(true)
    expect(skipped.some((s) => s.name === '飞讯')).toBe(true)
    expect(skipped.some((s) => s.name === '禁用的')).toBe(true)
    expect(cardHasMvuStateScripts(FIXTURE_CARD)).toBe(true)
    expect(cardHasMvuStateScripts({})).toBe(false)
  })
})

describe('Bridge 协议处理器', () => {
  it('load / apply 回传', async () => {
    const { Mvu } = mvuWithDerive()
    Mvu.setStatData({})
    const sent = []
    const { handleMessage } = createBridge(Mvu, { post: (m) => sent.push(m), loadScripts: async () => {} })
    await handleMessage({ __mvu: MVU_MSG, type: 'load', scripts: [] })
    expect(sent.at(-1)).toMatchObject({ type: 'loaded', ok: true })
    await handleMessage({ __mvu: MVU_MSG, id: 'x', type: 'apply', base_stat: { 角色: { 甲: { 好感: 88 } } }, raw_reply: '' })
    expect(sent.at(-1)).toMatchObject({ id: 'x', type: 'settled' })
    expect(sent.at(-1).stat_data.角色.甲._态度).toBe('亲近')
  })

  it('apply 应用 double_ai_ops（double_ai 策略主路径：正文无 <UpdateVariable>、tool_calls 空）', async () => {
    const { Mvu } = mvuWithDerive()
    Mvu.setStatData({})
    const sent = []
    const { handleMessage } = createBridge(Mvu, { post: (m) => sent.push(m), loadScripts: async () => {} })
    await handleMessage({
      __mvu: MVU_MSG, id: 'd', type: 'apply',
      base_stat: { 角色: { 甲: { 好感: 40 } } },
      raw_reply: '（纯叙事，无更新块）', tool_calls: [],
      double_ai_ops: [{ op: 'replace', path: '/角色/甲/好感', value: 88 }],
    })
    const s = sent.at(-1)
    expect(s.type).toBe('settled')
    expect(s.stat_data.角色.甲.好感).toBe(88) // double_ai_ops 生效
    expect(s.stat_data.角色.甲._态度).toBe('亲近') // 派生跟着更新
    expect(s.diag.applied).toBe(1)
  })
})

describe('MvuHostController 透传 double_ai_ops（断点回归）', () => {
  it('applyTurn 把 double_ai_ops 放进 apply 消息，不丢', () => {
    const sent = []
    const c = new MvuHostController({ send: (m) => sent.push(m) })
    const ops = [{ op: 'replace', path: '/a', value: 1 }]
    c.applyTurn({ base_stat: {}, raw_reply: '', tool_calls: [], double_ai_ops: ops })
    expect(sent.at(-1).double_ai_ops).toEqual(ops)
  })
})

describe('MvuHostController loadCard 透传 dangerous（卡驱动写入对话门控）', () => {
  it('loadCard 把 dangerous 写进 load 消息；缺省 false', async () => {
    const sent = []
    const c = new MvuHostController({ send: (m) => sent.push(m) })
    c.onMessage({ __mvu: MVU_MSG, type: 'ready' })
    await c.ready()
    void c.loadCard([{ name: 's', code: 'x', kind: 'logic' }], { dangerous: true })
    await tick() // loadCard 先 await this._ready 再 _send，等微任务冲刷
    expect(sent.at(-1)).toMatchObject({ type: 'load', dangerous: true })
    void c.loadCard([]) // 缺省
    await tick()
    expect(sent.at(-1)).toMatchObject({ type: 'load', dangerous: false })
  })
})

describe('MvuHostController correlation', () => {
  it('ready/load/apply 按 id 对应，error/dispose 拒绝', async () => {
    const sent = []
    const c = new MvuHostController({ send: (m) => sent.push(m) })
    c.onMessage({ __mvu: MVU_MSG, type: 'ready' })
    await c.ready()
    const lp = c.loadCard([{ name: 's', code: 'x', kind: 'logic' }])
    await tick()
    c.onMessage({ __mvu: MVU_MSG, type: 'loaded', ok: true })
    expect(await lp).toBe(true)
    const ap = c.applyTurn({ base_stat: { a: 1 } })
    const id = sent.at(-1).id
    c.onMessage({ __mvu: MVU_MSG, id, type: 'settled', stat_data: { a: 2 }, diag: {} })
    expect((await ap).stat_data.a).toBe(2)
    const ep = c.applyTurn({})
    c.onMessage({ __mvu: MVU_MSG, id: sent.at(-1).id, type: 'error', error: 'boom' })
    await expect(ep).rejects.toThrow(/boom/)
  })
})

describe('MvuHostSession 编排', () => {
  it('init 载脚本 + applyTurn + 空卡不建 iframe', async () => {
    const fakeFactory = () => ({
      controller: {
        ready: async () => {},
        loadCard: async () => {},
        applyTurn: async (sync) => ({ stat_data: { ...(sync.base_stat || {}), ok: true }, diag: {} }),
        dispose: () => {},
      },
      iframe: {},
    })
    const sess = new MvuHostSession({ hostFactory: fakeFactory })
    const r = await sess.init(FIXTURE_CARD)
    expect(r.ok).toBe(true)
    expect(r.scripts.length).toBe(3)
    expect((await sess.applyTurn({ base_stat: { x: 1 } })).stat_data.ok).toBe(true)
    sess.dispose()
    expect(sess.loaded).toBe(false)

    const sess2 = new MvuHostSession({ hostFactory: () => { throw new Error('nope') } })
    expect((await sess2.init({})).ok).toBe(false)
  })
})

describe('ADR-0008d 能力限权', () => {
  it('classifyCapability: local/read/dangerous', () => {
    expect(classifyCapability('generateRaw')).toBe('dangerous')
    expect(classifyCapability('setChatMessages')).toBe('dangerous')
    expect(classifyCapability('createChatMessages')).toBe('dangerous')
    expect(classifyCapability('deleteChatMessages')).toBe('dangerous')
    expect(classifyCapability('sendMessage')).toBe('dangerous') // 卡驱动写入对话
    expect(classifyCapability('getWorldbook')).toBe('read')
    expect(classifyCapability('getChatMessages')).toBe('read') // ADR-0008d：读会话楼层
    expect(classifyCapability('getVariables', { type: 'global' })).toBe('read')
    expect(classifyCapability('getVariables', { type: 'message' })).toBe('local')
    expect(classifyCapability('somethingWeird')).toBe('unknown')
  })

  it('resolveCapability: dangerous 默认拒，read 默认允，opt-in 放行', () => {
    expect(resolveCapability('generateRaw').allow).toBe(false)
    expect(resolveCapability('getWorldbook').allow).toBe(true)
    expect(resolveCapability('generateRaw', { dangerous: true }).allow).toBe(true)
    expect(resolveCapability('sendMessage').allow).toBe(false) // 卡发消息默认拒
    expect(resolveCapability('sendMessage', { dangerous: true }).allow).toBe(true) // 对话 opt-in 放行
    expect(resolveCapability('getWorldbook', { read: false }).allow).toBe(false)
    expect(resolveCapability('unknownCap').allow).toBe(false)
  })

  it('Bridge requestCap ↔ controller capabilityHandler round-trip（放行 + 拒绝）', async () => {
    const { Mvu } = mvuWithDerive()
    // 父：按 resolveCapability 裁决；dangerous 需 policy 开
    const policy = { dangerous: false }
    const controller = new MvuHostController({
      send: (m) => bridge.handleMessage(m), // 父→Host 直连
      capabilityHandler: async (cap, args) => {
        const r = resolveCapability(cap, policy, args)
        if (!r.allow) throw new Error(r.reason)
        return { ok: cap } // 模拟后端执行结果
      },
    })
    const bridge = createBridge(Mvu, { post: (m) => controller.onMessage(m), loadScripts: async () => {} })

    // read：允许
    await expect(bridge.requestCap('getWorldbook', { book: 'b' })).resolves.toEqual({ ok: 'getWorldbook' })
    // dangerous：默认拒
    await expect(bridge.requestCap('generateRaw', {})).rejects.toThrow(/default-denied/)
    // 开 policy 后放行
    policy.dangerous = true
    await expect(bridge.requestCap('generateRaw', {})).resolves.toEqual({ ok: 'generateRaw' })
  })

  it('prepareCardCode: schema 去 mvu_zod import / ui 重写 window.parent→window', () => {
    const schema = prepareCardCode({ kind: 'schema', code: "import { registerMvuSchema } from 'x/mvu_zod.js';\nconst S=1" })
    expect(schema).not.toMatch(/import/)
    expect(schema).toMatch(/const S=1/)
    const ui = prepareCardCode({ kind: 'ui', code: 'const p$ = window.parent.$ || window.$; const w = window.top;' })
    expect(ui).not.toMatch(/window\.parent/)
    expect(ui).not.toMatch(/window\.top/)
    expect(ui).toMatch(/window\.\$ \|\| window\.\$/)
  })

  it('stripModuleSyntax: 通用 ESM→classic（覆盖伶伶/WuWa/魔法少女 schema 真实形态）', () => {
    // 真卡 schema 统一形态：mvu_zod 具名 import + `export const Schema` + $(ready) 注册
    const real = [
      "import { registerMvuSchema } from 'https://cdn.jsdelivr.net/gh/StageDog/tavern_resource/dist/util/mvu_zod.js';",
      '',
      'export const Schema = z.object({ 好感度: z.coerce.number().transform(v => _.clamp(v, 0, 100)) });',
      '',
      '$(() => { registerMvuSchema(Schema); });',
    ].join('\n')
    const out = stripModuleSyntax(real)
    expect(out).not.toMatch(/^\s*import\b/m) // 静态 import 全剥
    expect(out).not.toMatch(/\bexport\b/)    // export 关键字剥掉
    expect(out).toMatch(/const Schema = z\.object/) // 声明保留
    expect(out).toMatch(/registerMvuSchema\(Schema\)/) // 注册调用保留（走全局 shim）
    // 包成 IIFE 后应能被 JS 引擎解析（不再是模块语法）
    expect(() => new Function(`(function(){\n${out}\n});`)).not.toThrow()
  })

  it('stripModuleSyntax: 剥各种 import/export 形态但保留动态 import()', () => {
    const s = stripModuleSyntax([
      "import 'https://x/bundle.js';",
      "import def from 'a';",
      "import * as ns from 'b';",
      "import { a, b } from 'c';",
      'export default foo;',
      'export { a, b };',
      'export function calc() { return 1; }',
      "const later = () => import('https://x/jquery-ui/+esm');", // 动态 import 必须保留
    ].join('\n'))
    expect(s).not.toMatch(/^\s*import\s+[^(]/m) // 静态 import 全无
    expect(s).not.toMatch(/^\s*export\b/m)      // export 语句全无
    expect(s).toMatch(/function calc\(\)/)       // 声明体保留
    expect(s).toMatch(/import\('https:\/\/x\/jquery-ui/) // 动态 import 保留
  })

  it('extractMvuScripts includeUi: 开关纳入 UI 脚本', () => {
    expect(extractMvuScripts(FIXTURE_CARD).scripts.some((s) => s.kind === 'ui')).toBe(false)
    const withUi = extractMvuScripts(FIXTURE_CARD, { includeUi: true })
    expect(withUi.scripts.some((s) => s.kind === 'ui')).toBe(true)
  })

  it('makeCapabilityHandler: read 放行取 provider / dangerous 默认拒 / opt-in 放行', async () => {
    const h = makeCapabilityHandler({ policy: { dangerous: false }, providers: { getWorldbook: async () => [{ x: 1 }] } })
    await expect(h('getWorldbook', {})).resolves.toEqual([{ x: 1 }]) // provider
    await expect(h('getWorldInfo', {})).resolves.toEqual([]) // 无 provider → 安全默认
    await expect(h('generateRaw', {})).rejects.toThrow(/default-denied/) // dangerous 拒
    const h2 = makeCapabilityHandler({ policy: { dangerous: true }, providers: { generateRaw: async () => 'reply' } })
    await expect(h2('generateRaw', {})).resolves.toBe('reply') // opt-in + provider
  })

  it('MvuHostSession includeUi + capabilityHandler 透传', async () => {
    let gotOpts = null
    const factory = (_url, opts) => { gotOpts = opts; return { controller: { ready: async () => {}, loadCard: async () => {}, applyTurn: async () => ({ stat_data: {}, diag: {} }), dispose: () => {} }, iframe: {} } }
    const capH = async () => null
    const { MvuHostSession } = await import('./mvu-host-session.mjs')
    const sess = new MvuHostSession({ hostFactory: factory, includeUi: true, capabilityHandler: capH })
    const r = await sess.init(FIXTURE_CARD)
    expect(r.scripts.some((s) => s.kind === 'ui')).toBe(true) // includeUi 生效
    expect(gotOpts.capabilityHandler).toBe(capH) // handler 透传给 factory
  })
})

describe('th-api: 卡驱动"写入对话" triggerSlash /send → sendMessage 能力', () => {
  it('/send <文本> 路由到 sendMessage 能力；非 /send 与空 /send 不发', async () => {
    const calls = []
    const requestCap = (cap, args) => { calls.push([cap, args]); return Promise.resolve('') }
    const win = {}
    installTavernHelperApi(win, { requestCap })

    await win.triggerSlash('/send 你好世界')
    expect(calls).toEqual([['sendMessage', { text: '你好世界' }]])

    calls.length = 0
    await win.triggerSlash('/echo x') // 其余 slash：安全降级，不发消息
    await win.triggerSlash('/send   ') // 空 /send：不发
    expect(calls).toEqual([])
  })

  it('/send 被拒时传播 rejection（不静默假成功，让卡走降级）', async () => {
    const win = {}
    installTavernHelperApi(win, { requestCap: () => Promise.reject(new Error('dangerous default-denied')) })
    await expect(win.triggerSlash('/send hi')).rejects.toThrow(/default-denied/)
  })
})
