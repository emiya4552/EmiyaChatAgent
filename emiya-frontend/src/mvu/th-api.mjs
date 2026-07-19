// TavernHelper 兼容层 —— 照酒馆助手官方 @types 实现的**完整 window API 表面**（137 个函数）。
//
// 方向（见 docs/mvu/direction-and-progress.md）：真·酒馆助手耦合 ST 本体、跑不了独立实例；
// 但它把 API 作为**有文档、版本化的 @types**（github.com/N0VI028/JS-Slash-Runner `@types/function/*`）
// 发布给卡作者。故正解是**照 @types 一次性实现整个表面**，把"按单卡补的打地鼠"变成"跟着 @types
// 版本周期性同步"。这样任何卡都不会再撞"函数未定义"。
//
// 分档：
//  - **真实现**：变量（→薄 Mvu 的 stat_data）、生成/楼层读写（→能力桥，dangerous 默认拒）。
//  - **安全降级**：世界书/角色/人设/预设/正则/音频/扩展等——按 @types 返回**正确形状**的空值
//    （`[]`/`{}`/`null`/`Promise.resolve`/`false`/`''`），卡 UI 拿到合法形状即可继续，只是效果不落地。
//
// 同步维护：酒馆助手发新版 → 对照其 @types 增补本文件（而非等卡报错）。

export function installTavernHelperApi(win, { requestCap } = {}) {
  const cap = typeof requestCap === 'function' ? requestCap : () => Promise.reject(new Error('no bridge'))
  const P = (v) => Promise.resolve(v)
  const statData = () => (win.Mvu && win.Mvu.getStatData && win.Mvu.getStatData()) || {}
  const mvuData = (opt) => (win.Mvu && win.Mvu.getMvuData ? win.Mvu.getMvuData(opt) : { stat_data: statData(), initialized_lorebooks: {} })

  const api = {
    // ─────────── 变量（真实现：→ 薄 Mvu 的 stat_data）───────────
    getVariables: (opt) => (opt && opt.type === 'global'
      ? cap('getVariables', opt) // 全局会话变量走后端（read）
      : mvuData(opt)),            // message/chat/character → 本回合 MvuData（同步，符合 @types）
    replaceVariables: (vars, _opt) => { try { win.Mvu && win.Mvu.setStatData && win.Mvu.setStatData((vars && vars.stat_data) || vars || {}) } catch (e) {} },
    insertOrAssignVariables: (vars, _opt) => { const sd = statData(); Object.assign(sd, (vars && vars.stat_data) || vars || {}); return { stat_data: sd } },
    insertVariables: (vars, _opt) => { const sd = statData(); Object.assign(sd, (vars && vars.stat_data) || vars || {}); return { stat_data: sd } },
    updateVariablesWith: (updater, _opt) => { try { const sd = statData(); if (typeof updater === 'function') updater(sd); return { stat_data: sd } } catch (e) { return { stat_data: statData() } } },
    deleteVariable: (path) => { try { const sd = statData(); if (path != null && path in sd) delete sd[path] } catch (e) {} return P() },
    registerVariableSchema: () => P(),

    // ─────────── 生成（真实现：→ 能力桥；dangerous 默认拒）───────────
    generate: (config) => cap('generate', config),
    generateRaw: (config) => cap('generateRaw', config),
    stopAllGeneration: () => true,
    stopGenerationById: () => true,
    getModelList: () => [],
    getProxyPresetNames: () => [],
    injectPrompts: () => P(),
    uninjectPrompts: () => P(),

    // ─────────── 楼层消息（读→桥；写→dangerous 桥）───────────
    getChatMessages: (range, opts) => cap('getChatMessages', { range, opts }),
    setChatMessages: (msgs, opts) => cap('setChatMessages', { msgs, opts }),
    createChatMessages: (msgs, opts) => cap('createChatMessages', { msgs, opts }),
    deleteChatMessages: (ids, opts) => cap('deleteChatMessages', { ids, opts }),
    rotateChatMessages: (a, b, opts) => cap('rotateChatMessages', { a, b, opts }),
    refreshOneMessage: () => P(),
    getMessageId: () => 0,
    getLastMessageId: () => 0,

    // ─────────── 世界书 / lorebook（读→桥/空；写→安全降级）───────────
    getWorldbook: (name) => cap('getWorldbook', { book: name }),
    getWorldbookNames: () => [],
    getGlobalWorldbookNames: () => [],
    getCharWorldbookNames: () => ({ primary: null, additional: [] }),
    getChatWorldbookName: () => null,
    getOrCreateChatWorldbook: () => P(''),
    createWorldbook: () => P(false),
    createOrReplaceWorldbook: () => P(false),
    deleteWorldbook: () => P(false),
    replaceWorldbook: () => P(),
    updateWorldbookWith: () => P(),
    createWorldbookEntries: () => P({ worldbook: [], new_entries: [] }),
    deleteWorldbookEntries: () => P({ worldbook: [], deleted_entries: [] }),
    createLorebook: () => P(false),
    deleteLorebook: () => P(false),
    getLorebooks: () => [],
    getChatLorebook: () => null,
    getCurrentCharPrimaryLorebook: () => null,
    getOrCreateChatLorebook: () => P(''),
    setChatLorebook: () => P(),
    getLorebookSettings: () => ({}),
    setLorebookSettings: () => P(),
    getLorebookEntries: () => P([]),
    setLorebookEntries: () => P(),
    createLorebookEntries: () => P({ lorebook: [], new_entries: [] }),
    deleteLorebookEntries: () => P({ lorebook: [], deleted_entries: [] }),
    replaceLorebookEntries: () => P(),
    getCharLorebooks: () => ({ primary: null, additional: [] }),
    setCurrentCharLorebooks: () => P(),
    rebindGlobalWorldbooks: () => P(),
    rebindCharWorldbooks: () => P(),
    rebindChatWorldbook: () => P(),

    // ─────────── 角色（安全降级：当前角色/空）───────────
    getCharData: () => null,
    getCharacter: () => null,
    getCharacterIds: () => [],
    getCharacterNames: () => [],
    getCurrentCharacterId: () => 0,
    getCurrentCharacterName: () => '',
    getCharAvatarPath: () => '',
    createCharacter: () => P(false),
    deleteCharacter: () => P(false),
    replaceCharacter: () => P(false),
    createOrReplaceCharacter: () => P(false),
    updateCharacterWith: () => P(),
    importRawCharacter: () => P(false),

    // ─────────── 人设（安全降级）───────────
    getPersona: () => null,
    getPersonaIds: () => [],
    getPersonaNames: () => [],
    getCurrentPersonaId: () => '',
    getCurrentPersonaName: () => '',
    getPersonaAvatarPath: () => '',
    createPersona: () => P(false),
    createOrReplacePersona: () => P(false),
    deletePersona: () => P(false),
    replacePersona: () => P(false),
    updatePersonaWith: () => P(),

    // ─────────── 预设（安全降级）───────────
    getPreset: () => null,
    getPresetNames: () => [],
    getLoadedPresetName: () => '',
    loadPreset: () => false,
    setPreset: () => P(),
    createPreset: () => P(false),
    createOrReplacePreset: () => P(false),
    deletePreset: () => P(false),
    renamePreset: () => P(false),
    replacePreset: () => P(),
    updatePresetWith: () => P(),
    importRawPreset: () => P(false),
    isPresetNormalPrompt: () => false,
    isPresetPlaceholderPrompt: () => false,
    isPresetSystemPrompt: () => false,

    // ─────────── 音频（安全降级：no-op）───────────
    playAudio: () => {},
    pauseAudio: () => {},
    getAudioList: () => [],
    getCurrentAudio: () => null,
    getAudioSettings: () => ({}),
    setAudioSettings: () => {},
    appendAudioList: () => {},
    replaceAudioList: () => {},

    // ─────────── 正则（安全降级）───────────
    getTavernRegexes: () => [],
    replaceTavernRegexes: () => P(),
    updateTavernRegexesWith: () => P(),
    isCharacterTavernRegexesEnabled: () => false,
    importRawTavernRegex: () => P(false),
    formatAsTavernRegexedString: (text) => String(text ?? ''),

    // ─────────── 宏 / 脚本按钮（安全降级）───────────
    registerMacroLike: () => {},
    unregisterMacroLike: () => {},
    getScriptTrees: () => [],
    replaceScriptTrees: () => P(),
    updateScriptTreesWith: () => P(),
    getAllEnabledScriptButtons: () => [],

    // ─────────── 扩展管理（安全降级）───────────
    installExtension: () => P(false),
    uninstallExtension: () => P(false),
    reinstallExtension: () => P(false),
    updateExtension: () => P(false),
    isInstalledExtension: () => false,
    getExtensionInstallationInfo: () => null,
    getExtensionType: () => '',
    isAdmin: () => false,
    getTavernHelperExtensionId: () => 'JS-Slash-Runner',

    // ─────────── 展示消息 / slash / 导入（安全降级）───────────
    formatAsDisplayedMessage: (text) => String(text ?? ''),
    retrieveDisplayedMessage: () => '',
    // `/send <文本>` → 卡替用户发消息 + 触发生成（sendMessage 能力，dangerous 默认拒）。
    // 放行则 resolve ''（@types 返回 Promise<string>）；被拒则**传播 rejection**（不静默假成功，
    // 让卡感知失败去走它的降级如剪贴板）。其余 slash 命令暂安全降级为 no-op。
    triggerSlash: (cmd) => {
      const s = String(cmd ?? '').trim()
      const m = /^\/send\b\s*([\s\S]*)$/i.exec(s)
      if (m && m[1].trim()) return cap('sendMessage', { text: m[1].trim() }).then(() => '')
      return P('')
    },
    importRawChat: () => P(false),
    importRawWorldbook: () => P(false),

    // ─────────── 版本 / 工具（真实现）───────────
    getTavernHelperVersion: () => '3.0.0-emiya-compat',
    getTavernVersion: () => '1.13.0',
    substitudeMacros: (text) => String(text ?? ''),
    errorCatched: (fn) => ((...args) => { try { return fn(...args) } catch (e) { console.warn('[MVU] errorCatched:', e); return undefined } }),
    initializeGlobal: () => P(),
  }

  // 装到裸 window 全局（卡多裸调）+ TavernHelper 命名空间（部分卡走命名空间）。
  // 不覆盖已存在的同名（如 installShims 里更贴合的 getVariables/eventOn 等），仅补空缺。
  win.TavernHelper = win.TavernHelper || {}
  for (const [k, fn] of Object.entries(api)) {
    if (typeof win[k] !== 'function') win[k] = fn
    if (typeof win.TavernHelper[k] !== 'function') win.TavernHelper[k] = fn
  }
  return api
}
