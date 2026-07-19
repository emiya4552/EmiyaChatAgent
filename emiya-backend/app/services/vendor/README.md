# Vendored JS（供后端 V8 沙箱 / mini-racer 加载）

这些是**预打包的 JS 库**，由 `js_ejs_engine.py`（世界书 EJS，ADR-0021）与
`mvu_runtime/schema_eval.py`（zod schema 初始默认值，ADR-0021 延伸）在 mini-racer（裸 V8，
无 ESM 模块加载器）里 `eval` 加载。故须是 **IIFE / 全局** 形态，不能是 ESM。

| 文件 | 是什么 | 如何重新生成 |
|---|---|---|
| `lodash.min.js` | lodash（全局 `_`） | 取自 npm `lodash/lodash.min.js`（UMD，直接 eval 即挂全局 `_`） |
| `zod-global.js` | zod v4（全局 `z`），~577KB | `npm i zod@^4` 后：`echo "import * as z from 'zod'; globalThis.z = z.z||z.default||z;" > e.js && esbuild e.js --bundle --format=iife --outfile=zod-global.js` |

升级时保持 zod 为 **v4**（卡的 schema 用 `.prefault()` 是 v4 特性）。
