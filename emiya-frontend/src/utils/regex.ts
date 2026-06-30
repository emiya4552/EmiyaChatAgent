import type { RegexScript } from '../types'

export function parseJsRegex(jsRegex: string): { pattern: string; flags: string } | null {
  if (!jsRegex.startsWith('/')) return null
  const lastSlash = jsRegex.lastIndexOf('/')
  if (lastSlash <= 0) return null
  return {
    pattern: jsRegex.slice(1, lastSlash),
    flags: jsRegex.slice(lastSlash + 1),
  }
}

export function applyRegexScripts(content: string, scripts: RegexScript[]): string {
  let result = content
  for (const script of scripts) {
    if (script.disabled) continue
    const parsed = parseJsRegex(script.findRegex)
    if (!parsed) continue
    try {
      const re = new RegExp(parsed.pattern, parsed.flags)
      result = result.replace(re, script.replaceString)
    } catch {
      // skip invalid regex silently
    }
  }
  return result
}
