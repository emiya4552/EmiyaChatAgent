import { marked, Renderer } from 'marked'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'

// 渲染管道：marked (markdown → HTML) → DOMPurify (sanitize) → 返回 HTML 字符串
// 详见 docs/adr/0008-frontend-rendering-and-css-theme.md

// ─── marked 配置 ───
// 禁用删除线（AI chat场景常用 ~ 表达语气，不应该被转成 <del>）
const renderer = new Renderer()
renderer.del = ({ text }: { text: string }) => text

// ```html 代码块且含整页 HTML 标记 → 输出占位 div，运行时由 mountHtmlIframes
// 替换为 iframe srcdoc。判定与酒馆助手 isFrontend 一致（详见 ADR-0012）。
function _isFrontendHtml(text: string): boolean {
  return text.includes('html>') || text.includes('<head>') || text.includes('<body')
}

function _isHtmlFragment(text: string, lang?: string): boolean {
  const normalizedLang = (lang || '').trim().toLowerCase()
  if (normalizedLang && normalizedLang !== 'html' && normalizedLang !== 'xml') {
    return false
  }

  const trimmed = text.trim()
  if (!trimmed.startsWith('<')) return false
  return /^<\/?[a-z][\w:-]*(?:\s|>|\/>)/i.test(trimmed)
}

function _utf8ToBase64(s: string): string {
  // 兼容中文：先转 UTF-8 percent encoding，再 base64
  return btoa(unescape(encodeURIComponent(s)))
}

const _defaultCodeRenderer = renderer.code.bind(renderer)
renderer.code = function (token: any) {
  const { text, lang } = token
  // 与酒馆助手 isFrontend 一致：只看 text 含 html>/<head>/<body 任一即视为前端代码块，
  // 不要求 lang 必须是 "html"（卡作者写 ```、```HTML、``` 都见过；放宽提升命中率）
  if (_isFrontendHtml(text)) {
    const b64 = _utf8ToBase64(text)
    return `<div class="th-html-render" data-content="${b64}"></div>`
  }
  // Some ST/MVU regex scripts wrap HTML fragments in plain fenced blocks:
  // ```\n<summary ...>...</summary>\n```
  // These are intended as sanitized in-message HTML, not developer code.
  if (_isHtmlFragment(text, lang)) {
    return text
  }
  return _defaultCodeRenderer(token)
}

marked.setOptions({
  renderer,
  breaks: true,
  gfm: true,
  highlight(code: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value
    }
    return hljs.highlightAuto(code).value
  },
} as any)

// ─── DOMPurify hooks（仅初始化一次） ───

let _hooksInstalled = false

function _installHooks(): void {
  if (_hooksInstalled) return
  _hooksInstalled = true

  // (1) 自定义元素全保留：ST 风卡里 <StatusBlock> / <dp1>~<dp8> / <ce1>~<ce4>
  // 等是 HTMLUnknownElement。DOMPurify 默认会删，hook 里强制保留。
  // 决策来源：ADR-0008 Q2=A（卡作者已被信任，标签全开）
  DOMPurify.addHook('uponSanitizeElement', (node, data) => {
    if (data.allowedTags[data.tagName]) return
    // HTMLUnknownElement: tagName 在标准白名单外但是合法的标识符
    const tag = data.tagName
    if (tag && /^[a-z][a-z0-9-]*$/i.test(tag)) {
      data.allowedTags[tag] = true
    }
  })

  // (2) <a> 标签强制 rel="noopener noreferrer" target="_blank"
  // 决策来源：ADR-0008 Q7a=B（外链允许但加隐私/安全护栏）
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A') {
      node.setAttribute('rel', 'noopener noreferrer')
      node.setAttribute('target', '_blank')
    }
  })
}

// ─── markdown-in-HTML 预处理 ───
// CommonMark 规范里，<details> 等 HTML 块标签开始后，直到 blank line 之前所有
// 内容都被视为原始 HTML，markdown 不处理。ST 卡的常见模式是
//   <details>
//   <summary>...</summary>
//   <br>
//   >第 1 行
//   >第 2 行
//   </details>
// 这里 `>` 是 markdown blockquote，但因为整段被视为 HTML 块没被转。
// 修复：把"纯 HTML 行"和"非 HTML 行"之间强行加 blank line，让 marked 把 HTML
// 块按 blank line 拆开，中间的 markdown 段独立处理后再拼回。

function _isHtmlOnlyLine(line: string): boolean {
  const t = line.trim()
  if (!t) return false
  // 一整行只由 HTML 标签构成（一个或多个，闭合或自闭合），无可见文字
  return /^<\/?[a-zA-Z][^>]*>(?:\s*<\/?[a-zA-Z][^>]*>)*$/.test(t)
}

function _enableMarkdownInHtmlBlocks(text: string): string {
  const lines = text.split('\n')
  const out: string[] = []
  for (let i = 0; i < lines.length; i++) {
    out.push(lines[i])
    const cur = lines[i]
    const nxt = lines[i + 1]
    if (nxt === undefined) break

    const curIsHtml = _isHtmlOnlyLine(cur)
    const nxtIsHtml = _isHtmlOnlyLine(nxt)
    const nxtIsBlank = nxt.trim() === ''

    // HTML 行 → 非 HTML 内容：插 blank line 让 HTML 块在此结束
    if (curIsHtml && !nxtIsHtml && !nxtIsBlank) {
      out.push('')
    }
    // 非 HTML 内容 → HTML 行：插 blank line 让 markdown 段在此结束
    if (!curIsHtml && cur.trim() !== '' && nxtIsHtml) {
      out.push('')
    }
  }
  return out.join('\n')
}

// ─── 公共 API ───

export function renderMarkdown(text: string): string {
  if (!text) return ''
  _installHooks()
  const prepared = _enableMarkdownInHtmlBlocks(text)
  const html = marked.parse(prepared) as string
  // FORBID_TAGS：iframe/embed/object 禁用（Q7b=A）；style 块默认删（Q7c=A）
  // ADD_TAGS 不需要 —— 自定义元素由 uponSanitizeElement hook 全保留
  return DOMPurify.sanitize(html, {
    FORBID_TAGS: ['iframe', 'embed', 'object', 'style'],
    FORBID_ATTR: ['srcdoc', 'sandbox'],
  })
}
