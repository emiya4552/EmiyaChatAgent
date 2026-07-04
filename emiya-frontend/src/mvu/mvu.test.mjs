// ADR-0008b/c 前端 MVU Host 单元测试（Vitest）。锁定各模块核心逻辑。
import { describe, it, expect } from 'vitest'
import {
  parseUpdateOps, toolCallsToOps, validateOps, applyOps, createThinMvu,
} from './mvu-runtime.mjs'
import { classifyMvuScript, extractMvuScripts, cardHasMvuStateScripts } from './card-scripts.mjs'
import { createBridge, MVU_MSG, prepareCardCode } from './mvu-host-bootstrap.mjs'
import { MvuHostController } from './mvu-host-controller.mjs'
import { MvuHostSession } from './mvu-host-session.mjs'
import { classifyCapability, resolveCapability } from './mvu-capabilities.mjs'

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
    expect(classifyCapability('getWorldbook')).toBe('read')
    expect(classifyCapability('getVariables', { type: 'global' })).toBe('read')
    expect(classifyCapability('getVariables', { type: 'message' })).toBe('local')
    expect(classifyCapability('somethingWeird')).toBe('unknown')
  })

  it('resolveCapability: dangerous 默认拒，read 默认允，opt-in 放行', () => {
    expect(resolveCapability('generateRaw').allow).toBe(false)
    expect(resolveCapability('getWorldbook').allow).toBe(true)
    expect(resolveCapability('generateRaw', { dangerous: true }).allow).toBe(true)
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

  it('extractMvuScripts includeUi: 开关纳入 UI 脚本', () => {
    expect(extractMvuScripts(FIXTURE_CARD).scripts.some((s) => s.kind === 'ui')).toBe(false)
    const withUi = extractMvuScripts(FIXTURE_CARD, { includeUi: true })
    expect(withUi.scripts.some((s) => s.kind === 'ui')).toBe(true)
  })
})
