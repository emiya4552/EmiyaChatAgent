# MVU Host（前端）— ADR-0008 浏览器内 MVU 运行时

把 MVU 卡的真实 JS（schema + `calculateStoryLogic`）跑在**前端跨源沙箱 iframe** 里，
在浏览器内完成层 2（解析/校验/clamp/只读）+ 层 3（派生 `_` 字段），后端只发 ops + 持久化。
背景见 `docs/mvu/adr/0008*`。

## 模块（均已 Node 验证核心逻辑）

| 文件 | 作用 | 验证 |
|---|---|---|
| `mvu-runtime.mjs` | 薄 Mvu 层：`parseUpdateOps`/`toolCallsToOps`/`validateOps`/`applyOps`/`createThinMvu`（`processTurn` 吃一回合 inline+tool 原料→应用→发 `VARIABLE_UPDATE_ENDED`） | Node ✅（含真卡 e2e，见 `.scratch/mvu-spike/e2e.html`） |
| `mvu-host-bootstrap.mjs` | 跑在 iframe 内：`installShims`（Vendored Stack + Host Shim：`waitGlobalInitialized`/`eventOn`/`registerMvuSchema`/`Mvu`/`SillyTavern`）+ `createBridge`（协议处理器）+ `bootMvuHost`（浏览器入口） | Bridge Node ✅ |
| `mvu-host-controller.mjs` | 父窗口：`MvuHostController`（`loadCard`/`applyTurn` 按 id correlate + `capabilityHandler` 裁决卡能力请求）+ `createIframeHost` | Vitest ✅ |
| `card-scripts.mjs` | 从 `card_data` 抽取/分类脚本（`extractMvuScripts`，`includeUi` 开关）| Vitest ✅（真卡） |
| `mvu-host-session.mjs` | 顶层编排 `MvuHostSession`（init/applyTurn/dispose）| Vitest ✅ |
| `mvu-capabilities.mjs` | **ADR-0008d** 能力分层 + 限权（`classifyCapability`/`resolveCapability`；dangerous 默认拒）| Vitest ✅ |

> 提交的验证：`src/mvu/mvu.test.mjs` = **16 Vitest 用例**（`npx vitest run src/mvu`）。

## Bridge 协议

```
父→Host:  {__mvu:1, type:'load',  scripts:[{name,code,kind:'schema'|'logic'|'data'}]}
          {__mvu:1, id, type:'apply', base_stat, raw_reply, tool_calls, constraints}
Host→父:  {__mvu:1, type:'ready'}
          {__mvu:1, type:'loaded', ok, error?}
          {__mvu:1, id, type:'settled', stat_data, diag} | {__mvu:1, id, type:'error', error}
能力(0008d): Host→父 {__mvu:1, type:'cap', id, cap, args}
             父→Host {__mvu:1, type:'cap-result', id, ok, result?|error?}   // 父按 resolveCapability 裁决
```

## 数据流（一回合）

后端 `message_done.mvu_browser_sync = {base_stat, raw_reply, tool_calls}`（`MvuBrowserSync`，
`settings.MVU_BROWSER_RUNTIME` 开时）→ 父 `controller.applyTurn(sync)` → Host `Mvu.processTurn`
→ 真卡 `calculateStoryLogic` 派生 → 回传结算 `stat_data`。

## 已就位（阶段 2b 大部分）

- **Host 页**：`emiya-frontend/mvu-host.html` + `mvu-host-entry.mjs`（跑 `bootMvuHost()`）；
  `vite.config.ts` 已加为多入口。iframe `src="/mvu-host.html" sandbox="allow-scripts"`。
- **卡脚本抽取**：`card-scripts.mjs::extractMvuScripts(persona.card_data)` → schema/logic/data
  （跳 MagVarUpdate bundle + UI）。已对真卡验证。
- **编排**：`MvuHostSession`（`init(cardData)` / `applyTurn(sync)` / `dispose()`）。

## 待接（最后一步：chat store 接线，需真实 app 验证）

`emiya-frontend/src/stores/chat.ts` 有**两个** `onDone`（主 SSE 路径 + live 广播路径），
变量同步在 `data?.variables !== undefined` 那段（约 line 107）。在两处都加：

```ts
// 会话打开时（切会话处）：取 persona.card_data → 建会话
//   const detail = await fetchPersonaDetail(conv.persona_id)
//   mvuSession = new MvuHostSession(); await mvuSession.init(detail.card_data)
// 切走 / 卸载时：mvuSession?.dispose()

// onDone 里（若开了 MVU_BROWSER_RUNTIME，后端会带 mvu_browser_sync）：
if (data?.mvu_browser_sync && mvuSession?.loaded) {
  const { stat_data } = await mvuSession.applyTurn(data.mvu_browser_sync) // 浏览器结算
  // 用 stat_data 覆盖对话状态变量展示（替代/优先于 data.variables）
  // TODO(0008c UP)：再把 stat_data POST 回后端持久化 + 下条请求携带
}
```

**剩余（阶段 3+）**：
- **跨源硬化**：CDN → 自托 Vendored Stack + CSP 锁 `script-src`/`connect-src`（`installShims` 已标 TODO）。
- **State Sync UP（ADR-0008c）**：结算 `stat_data` POST 回后端 + 下条请求携带 client 态；之后关后端 apply（退役）。
- **replay-on-load**：加载会话若状态未结算，对已存回复重跑 `applyTurn` 补算。
- **UI 子系统（ADR-0008d）**：`generateRaw`/`setChatMessages`/世界书面板/手机终端 + Bridge 限权。

> 注：`mvu-runtime.mjs` 与 `.scratch/mvu-spike/mvu-runtime.mjs` 是同源；spike 那份是历史验证台，
> 本目录这份是正式落地版（多了 `toolCallsToOps`/`processTurn`）。
