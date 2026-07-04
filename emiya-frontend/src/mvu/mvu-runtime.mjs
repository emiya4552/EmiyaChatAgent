// 薄 EMIYA Mvu 层 —— ADR-0008b option B 的核心可复用运行时。
//
// 层 2 引擎：解析 <UpdateVariable> → 校验(_只读/coerce/clamp) → 应用 JSONPatch →
// 发 VARIABLE_UPDATE_ENDED（卡的 calculateStoryLogic 监听器在此算层 3 派生）。
//
// 移植自后端 Python（不新发明）：
//   - 解析 + JSONPatch 原语：app/services/message_pipeline.py（ADR-0006）
//   - 校验 validate_ops：app/services/mvu_runtime/update_core.py（ADR-0005）
//
// 层 1（发射）仍在后端产出 ops（inline `<UpdateVariable>` + 可选 tool 通道），随
// message_done 的 `mvu_browser_sync` 下推（ADR-0008c）；本层只解析+应用+发事件。

// ============================================================
// 解析（ADR-0006：message_pipeline 的宽容 <UpdateVariable> 解析）
// ============================================================
const UPDATE_VAR_RE = /<UpdateVariable\b[^>]*>([\s\S]*?)<\/UpdateVariable>/gi
const JSON_PATCH_RE = /<(?:JSONPatch|json_patch)\b[^>]*>([\s\S]*?)<\/(?:JSONPatch|json_patch)>/i
const ANALYSIS_RE = /<Analysis\b[^>]*>[\s\S]*?<\/Analysis>/gi

// 从 s 里找第一个配平的 [...]（考虑字符串与转义）。port _find_balanced_array。
function findBalancedArray(s) {
  const start = s.indexOf('[')
  if (start === -1) return null
  let depth = 0, inStr = false, esc = false
  for (let i = start; i < s.length; i++) {
    const ch = s[i]
    if (inStr) {
      if (esc) esc = false
      else if (ch === '\\') esc = true
      else if (ch === '"') inStr = false
      continue
    }
    if (ch === '"') inStr = true
    else if (ch === '[') depth++
    else if (ch === ']') { depth--; if (depth === 0) return s.slice(start, i + 1) }
  }
  return null
}

// 从一个 <UpdateVariable> 块里取 JSONPatch 数组文本。port _extract_patch_array_text。
function extractPatchArrayText(block) {
  const m = JSON_PATCH_RE.exec(block)
  if (m) return m[1]
  const stripped = block.replace(ANALYSIS_RE, '')
  return findBalancedArray(stripped)
}

// 解析整段回复里所有 <UpdateVariable> → 规范化 ops[]。
export function parseUpdateOps(text) {
  if (!text || text.indexOf('<UpdateVariable') === -1) return []
  const ops = []
  UPDATE_VAR_RE.lastIndex = 0
  let m
  while ((m = UPDATE_VAR_RE.exec(text)) !== null) {
    const arrText = extractPatchArrayText(m[1])
    if (!arrText) continue
    try {
      const parsed = JSON.parse(arrText)
      if (Array.isArray(parsed)) for (const op of parsed) if (op && typeof op === 'object') ops.push(op)
    } catch { /* 坏 JSON 丢弃，不阻断 */ }
  }
  return ops
}

// tool 通道（ADR-0005）：从 OpenAI tool_calls 里抽 update_variables 的 patch → ops。
// 对齐后端 tools.py::extract_update_ops_from_tool_calls（name='update_variables'，
// arguments 是 JSON 字符串 {patch:[...]}）。
export function toolCallsToOps(toolCalls) {
  const ops = []
  for (const tc of toolCalls || []) {
    const fn = (tc && tc.function) || {}
    if (fn.name !== 'update_variables') continue
    let args = fn.arguments
    try { if (typeof args === 'string') args = JSON.parse(args) } catch { continue }
    const patch = args && typeof args === 'object' ? args.patch : null
    if (Array.isArray(patch)) for (const o of patch) if (o && typeof o === 'object') ops.push(o)
  }
  return ops
}

// ============================================================
// JSON Pointer + 路径原语（ADR-0006）
// ============================================================
export function decodeJsonPointer(path) {
  if (!path) return []
  if (!String(path).startsWith('/')) path = '/' + path
  const parts = String(path).split('/').slice(1).map((p) => p.replace(/~1/g, '/').replace(/~0/g, '~'))
  return parts.length && parts[0] === 'stat_data' ? parts.slice(1) : parts
}

function containerFor(nextSeg) {
  return nextSeg != null && (/^\d+$/.test(String(nextSeg)) || nextSeg === '-') ? [] : {}
}

function listIndex(seg, length, appendAllowed = false) {
  if (seg === '-') return appendAllowed ? length : Math.max(length - 1, 0)
  let idx = parseInt(seg, 10)
  if (Number.isNaN(idx)) idx = appendAllowed ? length : Math.max(length - 1, 0)
  if (idx < 0) idx = Math.max(length + idx, 0)
  return idx
}

function resolveParent(root, path, create) {
  let cur = root
  for (let i = 0; i < path.length - 1; i++) {
    const seg = path[i]
    const nextSeg = i + 1 < path.length ? path[i + 1] : null
    if (Array.isArray(cur)) {
      const idx = listIndex(seg, cur.length, create)
      if (idx >= cur.length) {
        if (!create) return [null, null]
        while (cur.length <= idx) cur.push(null)
        cur[idx] = containerFor(nextSeg)
      }
      if (cur[idx] == null && create) cur[idx] = containerFor(nextSeg)
      cur = cur[idx]
    } else if (cur && typeof cur === 'object') {
      if (!(seg in cur) || cur[seg] == null) {
        if (!create) return [null, null]
        cur[seg] = containerFor(nextSeg)
      }
      cur = cur[seg]
    } else return [null, null]
  }
  return [cur, path.length ? path[path.length - 1] : null]
}

export function getPath(root, path) {
  let cur = root
  for (const seg of path) {
    if (Array.isArray(cur)) {
      const idx = listIndex(seg, cur.length)
      cur = idx >= 0 && idx < cur.length ? cur[idx] : undefined
    } else if (cur && typeof cur === 'object') cur = cur[seg]
    else return undefined
  }
  return cur
}

function setPath(root, path, value, insert = false) {
  if (!path.length) { if (value && typeof value === 'object' && !Array.isArray(value)) { for (const k of Object.keys(root)) delete root[k]; Object.assign(root, value) } return }
  const [parent, key] = resolveParent(root, path, true)
  if (parent == null || key == null) return
  if (Array.isArray(parent)) {
    const idx = listIndex(key, parent.length, true)
    if (insert || key === '-') parent.splice(Math.min(idx, parent.length), 0, value)
    else { while (parent.length <= idx) parent.push(null); parent[idx] = value }
  } else parent[key] = value
}

function removePath(root, path) {
  if (!path.length) return null
  const [parent, key] = resolveParent(root, path, false)
  if (parent == null || key == null) return null
  if (Array.isArray(parent)) { const idx = listIndex(key, parent.length); if (idx >= 0 && idx < parent.length) return parent.splice(idx, 1)[0]; return null }
  const old = parent[key]; delete parent[key]; return old
}

// ============================================================
// 校验（ADR-0005：update_core.validate_ops）
// ============================================================
const TRUE_SET = new Set(['true', '1', 'yes', 'y', '是', '真', 'on'])
const FALSE_SET = new Set(['false', '0', 'no', 'n', '否', '假', 'off'])
const VALUE_OPS = new Set(['add', 'replace', 'assign', 'set', 'insert', 'delta'])

function hasReadonlySeg(segs) { return segs.some((s) => String(s).startsWith('_')) }

function coerce(value, curFound, curValue, ctype) {
  let target = null
  if (curFound && curValue != null) {
    if (typeof curValue === 'boolean') target = 'boolean'
    else if (typeof curValue === 'number') target = 'number'
    else if (typeof curValue === 'string') target = 'string'
  }
  if (target == null) target = ctype
  if (target == null || value == null) return [value, false]
  try {
    if (target === 'boolean') {
      if (typeof value === 'boolean') return [value, false]
      const s = String(value).trim().toLowerCase()
      if (TRUE_SET.has(s)) return [true, true]
      if (FALSE_SET.has(s)) return [false, true]
      return [value, false]
    }
    if (target === 'number') {
      if (typeof value === 'boolean') return [value, false]
      if (typeof value === 'number') return [value, false]
      const num = Number(String(value).trim())
      if (Number.isNaN(num)) return [value, false]
      return [num, true]
    }
    if (target === 'string') {
      if (typeof value === 'string') return [value, false]
      return [String(value), true]
    }
  } catch { return [value, false] }
  return [value, false]
}

function applyRangeEnum(value, constraint) {
  if (!constraint) return [value, null]
  const enumv = constraint.enum
  if (enumv && typeof value === 'string' && !enumv.includes(value)) return [value, 'enum-drop']
  const lo = constraint.min, hi = constraint.max
  if (typeof value === 'number' && !Number.isNaN(value)) {
    let clamped = value
    if (lo != null && clamped < lo) clamped = lo
    if (hi != null && clamped > hi) clamped = hi
    if (clamped !== value) return [clamped, 'clamped']
  }
  return [value, null]
}

export function validateOps(statData, ops, constraints = {}) {
  const accepted = []
  const diag = { applied: 0, dropped: [], coerced: [], clamped: [] }
  for (let op of ops || []) {
    if (!op || typeof op !== 'object') { diag.dropped.push({ path: null, reason: 'op 非对象' }); continue }
    const kind = String(op.op || '').toLowerCase()
    const rawPath = String(op.path || '')
    const segs = decodeJsonPointer(rawPath)

    if (hasReadonlySeg(segs)) { diag.dropped.push({ path: rawPath, reason: '只读 `_` 路径' }); continue }
    if (kind === 'move' || kind === 'copy') {
      const fromSegs = decodeJsonPointer(String(op.from || op.source || ''))
      if (hasReadonlySeg(fromSegs)) { diag.dropped.push({ path: String(op.from || op.source || ''), reason: 'readonly `_` source' }); continue }
    }

    if (VALUE_OPS.has(kind) && 'value' in op) {
      const dot = segs.join('.')
      const constraint = constraints[dot]
      const ctype = constraint ? constraint.type : null
      const curFound = getPath(statData, segs) != null
      const curValue = getPath(statData, segs)
      const value = op.value
      let [newValue, wasCoerced] = coerce(value, curFound, curValue, ctype)
      if (wasCoerced) diag.coerced.push({ path: rawPath, from: value, to: newValue })

      if (kind === 'delta') {
        const curNum = typeof curValue === 'number' && !Number.isNaN(curValue) ? curValue : 0
        if (typeof newValue === 'number') {
          const [res, note] = applyRangeEnum(curNum + newValue, constraint)
          if (note === 'clamped') { diag.clamped.push({ path: rawPath, to: res }); newValue = res - curNum }
        }
      } else {
        const [res, note] = applyRangeEnum(newValue, constraint)
        if (note === 'enum-drop') { diag.dropped.push({ path: rawPath, reason: `枚举外值: ${value}` }); continue }
        if (note === 'clamped') { diag.clamped.push({ path: rawPath, to: res }); newValue = res }
      }
      op = { ...op, value: newValue }
    }
    accepted.push(op)
  }
  diag.applied = accepted.length
  return { accepted, diag }
}

// 应用已校验的 ops（ADR-0006：_apply_json_patch_ops 的写入部分）。
export function applyOps(statData, ops) {
  for (const op of ops) {
    if (!op || typeof op !== 'object') continue
    const kind = String(op.op || '').toLowerCase()
    const path = decodeJsonPointer(String(op.path || ''))
    try {
      if (['add', 'replace', 'assign', 'set'].includes(kind)) setPath(statData, path, structuredClone(op.value))
      else if (kind === 'insert') setPath(statData, path, structuredClone(op.value), true)
      else if (['remove', 'delete', 'unset'].includes(kind)) removePath(statData, path)
      else if (kind === 'delta') { const cur = getPath(statData, path) || 0; setPath(statData, path, cur + (op.value || 0)) }
      else if (kind === 'move' || kind === 'copy') {
        const source = decodeJsonPointer(String(op.from || op.source || ''))
        let value = structuredClone(getPath(statData, source))
        if (kind === 'move') value = removePath(statData, source)
        setPath(statData, path, value)
      }
    } catch (e) { console.warn('MVU JSONPatch op 应用失败', op, e) }
  }
}

// ============================================================
// 薄 Mvu 门面
// ============================================================
export function createThinMvu({ z = null, eventEmit } = {}) {
  let statData = {}
  let schema = null
  const events = {
    VARIABLE_UPDATE_STARTED: 'mvu:variable_update_started',
    VARIABLE_UPDATE_ENDED: 'mvu:variable_update_ended',
  }
  async function emit(name, ...args) { if (typeof eventEmit === 'function') await eventEmit(name, ...args) }

  function registerMvuSchema(s) {
    schema = s
    try { statData = s.parse({}) } catch (e) { console.warn('registerMvuSchema: schema.parse({}) 失败', e) }
    return s
  }

  const Mvu = {
    events,
    getMvuData() { return { stat_data: statData } },
    replaceMvuData(mvuData) { if (mvuData && mvuData.stat_data) statData = mvuData.stat_data; return mvuData },
    setStatData(s) { statData = s || {} },
    getStatData() { return statData },
    getSchema() { return schema },

    // 层 2 主入口：吃一段回复文本，跑通 解析→校验→应用→发事件（层3派生在监听器里）。
    async processReply(text, constraints = {}) {
      const oldStat = structuredClone(statData)
      const ops = parseUpdateOps(text)
      const { accepted, diag } = validateOps(statData, ops, constraints)
      applyOps(statData, accepted)
      const newWrap = { stat_data: statData }
      const oldWrap = { stat_data: oldStat }
      await emit(events.VARIABLE_UPDATE_STARTED, newWrap, oldWrap)
      await emit(events.VARIABLE_UPDATE_ENDED, newWrap, oldWrap)
      // 卡的监听器可能重写 vars.stat_data（script_3 normal path: vars.stat_data = processedData），
      // 也可能走 replaceMvuData。两者都收敛到这里。
      statData = newWrap.stat_data
      return { stat_data: statData, diag, ops: accepted }
    },

    // ADR-0008c down-channel 主入口：吃 message_done.mvu_browser_sync 的一回合原料
    // （base_stat + raw_reply(含 inline <UpdateVariable>) + tool_calls/double_ai_ops），source-agnostic。
    // 先 setStatData(base) 由调用方做；这里合并多路 ops → 校验 → 应用 → 发事件（层3派生）。
    async processTurn({ raw_reply = '', tool_calls = [], double_ai_ops = [], constraints = {} } = {}) {
      const oldStat = structuredClone(statData)
      const ops = [
        ...parseUpdateOps(raw_reply),
        ...toolCallsToOps(tool_calls),
        ...(Array.isArray(double_ai_ops) ? double_ai_ops : []),
      ]
      const { accepted, diag } = validateOps(statData, ops, constraints)
      applyOps(statData, accepted)
      const newWrap = { stat_data: statData }
      const oldWrap = { stat_data: oldStat }
      await emit(events.VARIABLE_UPDATE_STARTED, newWrap, oldWrap)
      await emit(events.VARIABLE_UPDATE_ENDED, newWrap, oldWrap)
      statData = newWrap.stat_data
      return { stat_data: statData, diag, ops: accepted }
    },
  }
  return { Mvu, registerMvuSchema, events }
}
