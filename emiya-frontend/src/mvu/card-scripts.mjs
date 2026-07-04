// 从 persona.card_data 里抽出 + 分类 MVU 卡脚本，喂给 MvuHostController.loadCard（ADR-0008c 阶段2b）。
//
// 卡的脚本在 `card_data.data.extensions.tavern_helper.scripts[]`（v3）或
// `card_data.extensions.tavern_helper.scripts[]`（扁平），每条 `{name, content, enabled, ...}`。
//
// 状态运行时（S1）只要 schema/logic/data；**跳过** MagVarUpdate 引擎 import（用薄 Mvu 层替代）
// 与纯 UI 子系统（0008d 再接）。分类是 best-effort：关键是跳掉 bundle-import（否则会去拉真
// bundle 而失败/挂起）；UI 误载也只是无头抛错被吞，不致命。

/** 分类一段脚本内容。返回 'bundle'|'schema'|'logic'|'ui'|'data'。
 * logic 优先于 ui：剧情逻辑核心自身也含面板 UI，但有 calculateStoryLogic → 归 logic 照常加载。*/
export function classifyMvuScript(content) {
  const c = String(content || '')
  if (/import\s+['"][^'"]*MagVarUpdate/.test(c)) return 'bundle'
  if (/registerMvuSchema/.test(c)) return 'schema'
  if (/calculateStoryLogic|VARIABLE_UPDATE_ENDED/.test(c)) return 'logic'
  if (/\bgenerateRaw\b|\bsetChatMessages\b|\bcreateChatMessages\b|\.draggable\b|appendInexistentScriptButtons/.test(c)) return 'ui'
  return 'data'
}

function scriptsFrom(cardData) {
  const data = (cardData && (cardData.data || cardData)) || {}
  const raw = data && data.extensions && data.extensions.tavern_helper && data.extensions.tavern_helper.scripts
  return Array.isArray(raw) ? raw : []
}

/**
 * @param cardData persona.card_data（原始卡 JSON）
 * @param opts.includeUi ADR-0008d UI 阶段=true 时也纳入 UI 脚本（kind='ui'）；状态阶段(默认)只 schema/logic/data。
 * @returns { scripts: [{name, code, kind}], skipped: [{name, reason}] }
 *   scripts 顺序保持卡内原序（schema 先注册、logic 后挂监听器依赖它）。
 */
export function extractMvuScripts(cardData, { includeUi = false } = {}) {
  const scripts = []
  const skipped = []
  for (const s of scriptsFrom(cardData)) {
    const name = (s && s.name) || ''
    const content = String((s && s.content) || '')
    if (s && s.enabled === false) { skipped.push({ name, reason: 'disabled' }); continue }
    if (!content.trim()) { skipped.push({ name, reason: 'empty' }); continue }
    const kind = classifyMvuScript(content)
    if (kind === 'bundle') { skipped.push({ name, reason: 'MagVarUpdate 引擎 import（薄 Mvu 层替代）' }); continue }
    if (kind === 'ui' && !includeUi) { skipped.push({ name, reason: 'UI 子系统（ADR-0008d，未开 includeUi）' }); continue }
    scripts.push({ name, code: content, kind }) // schema | logic | data | ui
  }
  return { scripts, skipped }
}

/** 便捷判定：这张卡有没有可跑的 MVU 状态脚本（至少一个 schema/logic）。*/
export function cardHasMvuStateScripts(cardData) {
  const { scripts } = extractMvuScripts(cardData)
  return scripts.some((s) => s.kind === 'schema' || s.kind === 'logic')
}
