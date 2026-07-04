// MVU Host iframe 的入口脚本（被 mvu-host.html 以 module 加载）。
// 一跑就装环境+薄 Mvu 层+接 Bridge，然后 postMessage 'ready' 给父窗口。
// 见 mvu-host-bootstrap.mjs 与 src/mvu/README.md。
import { bootMvuHost } from './mvu-host-bootstrap.mjs'

bootMvuHost().catch((e) => {
  // 装配失败也告知父窗口，避免父端一直等 ready
  try {
    window.parent.postMessage({ __mvu: 1, type: 'ready', error: String((e && e.stack) || e) }, '*')
  } catch { /* ignore */ }
  console.error('[MVU Host] boot 失败:', e)
})
