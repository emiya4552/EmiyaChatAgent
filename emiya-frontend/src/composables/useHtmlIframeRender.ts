// 把 markdown 渲染输出里的 `<div class="th-html-render" data-content="base64">`
// 占位元素替换为 `<iframe srcdoc="...">`，让 LLM 输出的整页 HTML 在样式隔离的
// 沙箱里跑（CSS 渐变 / fontawesome 图标 / 外链字体等都能用）。
//
// 详见 ADR-0012「LLM 前端美化代码块的 iframe 渲染」。
//
// 流程：
//   markdown.ts::renderer.code  →  <div.th-html-render data-content="b64">
//   DOMPurify  →  保留（div + class + data-* 默认在白名单）
//   v-html  →  挂到 DOM
//   StreamingText (非流式期) →  nextTick → mountHtmlIframes(rootEl)
//
// iframe 内通过 postMessage 把 scrollHeight 上报，父监听 message 调 iframe.height。

const HEIGHT_SCRIPT = `
<script>
(function () {
  function reportHeight() {
    var h = document.documentElement.scrollHeight || document.body.scrollHeight || 0;
    try {
      window.parent.postMessage({ __th_iframe: true, type: 'height', height: h }, '*');
    } catch (e) {}
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', reportHeight);
  } else {
    reportHeight();
  }
  window.addEventListener('load', reportHeight);
  if (typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(reportHeight).observe(document.documentElement);
  }
  // 兜底：每 500ms 复测一次直到 5s，应对外链字体加载完后高度突变
  var n = 0;
  var iv = setInterval(function () {
    n++;
    reportHeight();
    if (n >= 10) clearInterval(iv);
  }, 500);
})();
</script>
`

const BASE_STYLE = `
<style>
*, *::before, *::after { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  max-width: 100%;
  overflow-x: hidden;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans SC', sans-serif;
}
body { background: transparent; }
</style>
`

function _base64ToUtf8(b64: string): string {
  try {
    return decodeURIComponent(escape(atob(b64)))
  } catch {
    try {
      return atob(b64)
    } catch {
      return ''
    }
  }
}

function _buildSrcdoc(userHtml: string): string {
  // 如果 LLM 已经给了完整 <!DOCTYPE><html>...</html>，在 <head> 里追加我们的脚本与样式；
  // 否则包装一层完整文档。
  const isFullDoc = /<html[\s>]/i.test(userHtml) || /<!DOCTYPE/i.test(userHtml)
  if (isFullDoc) {
    // 在 </head> 之前注入；如果没有 <head>，在 <html> 之后注入
    if (/<\/head>/i.test(userHtml)) {
      return userHtml.replace(/<\/head>/i, `${BASE_STYLE}${HEIGHT_SCRIPT}</head>`)
    }
    if (/<head[\s>]/i.test(userHtml)) {
      return userHtml.replace(/<head[\s>][^>]*>/i, (m) => `${m}${BASE_STYLE}${HEIGHT_SCRIPT}`)
    }
    // 极端：有 <html> 没 <head>
    return userHtml.replace(/<html[^>]*>/i, (m) => `${m}<head>${BASE_STYLE}${HEIGHT_SCRIPT}</head>`)
  }
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
${BASE_STYLE}
${HEIGHT_SCRIPT}
</head>
<body>${userHtml}</body>
</html>`
}

// 全局 message listener 单例 —— 多个 iframe 共享同一个监听器
let _listenerInstalled = false
const _iframeRegistry = new WeakMap<MessageEventSource, HTMLIFrameElement>()

function _ensureListener(): void {
  if (_listenerInstalled) return
  _listenerInstalled = true
  window.addEventListener('message', (ev: MessageEvent) => {
    const data = ev.data
    if (!data || typeof data !== 'object' || data.__th_iframe !== true) return
    if (data.type !== 'height') return
    if (!ev.source) return
    const iframe = _iframeRegistry.get(ev.source)
    if (!iframe) return
    const h = Number(data.height) || 0
    if (h > 0) {
      // 加 4px 余量避免轻微滚动条出现
      iframe.style.height = `${h + 4}px`
    }
  })
}

export function mountHtmlIframes(root: HTMLElement | null | undefined): void {
  if (!root) return
  _ensureListener()

  const placeholders = root.querySelectorAll<HTMLDivElement>(
    'div.th-html-render:not([data-th-mounted])',
  )
  placeholders.forEach((ph) => {
    const b64 = ph.getAttribute('data-content') || ''
    const userHtml = _base64ToUtf8(b64)
    if (!userHtml) return

    const iframe = document.createElement('iframe')
    iframe.setAttribute('loading', 'lazy')
    iframe.setAttribute('frameborder', '0')
    iframe.style.width = '100%'
    // 初始 400px 骨架——postMessage 收到真实 scrollHeight 后会被覆盖（见
    // _ensureListener）。比之前 120px 更接近野生卡的常见状态栏高度，
    // 减少加载瞬间的"小气泡"观感。
    iframe.style.height = '400px'
    iframe.style.border = '0'
    iframe.style.borderRadius = '8px'
    iframe.style.background = 'transparent'
    iframe.srcdoc = _buildSrcdoc(userHtml)

    iframe.addEventListener('load', () => {
      if (iframe.contentWindow) {
        _iframeRegistry.set(iframe.contentWindow, iframe)
      }
    })

    ph.setAttribute('data-th-mounted', '1')
    ph.replaceChildren(iframe)
  })
}

// 用户偏好：localStorage 控制开关，默认 true
const STORAGE_KEY = 'emiya_render_html_iframe'

export function isHtmlIframeRenderEnabled(): boolean {
  const v = localStorage.getItem(STORAGE_KEY)
  return v === null ? true : v === 'true'
}

export function setHtmlIframeRenderEnabled(enabled: boolean): void {
  localStorage.setItem(STORAGE_KEY, String(enabled))
}
