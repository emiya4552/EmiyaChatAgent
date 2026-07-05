import { fileURLToPath } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

// ADR-0008b（修订）：把 MVU Host 打成**单文件自包含 bundle**，经 srcdoc 内联注入沙箱 iframe。
// 虚拟模块 `virtual:mvu-host-bundle` 的默认导出 = bundle 源码字符串（供 createIframeHost 内联）。
// 为何不再用 <iframe src="/mvu-host.html">：opaque 源（allow-scripts 无 allow-same-origin）按 CORS
// 模式 fetch 同源 module 脚本会被拦 → Host 从未 boot。内联脚本无 fetch，隔离照旧、无 CORS。
// jsdelivr 的 `import('https://…')` 作为外部依赖保留（跨源 CORS，jsdelivr 回 ACAO:* 放行）。
function mvuHostBundlePlugin(): Plugin {
  const virtualId = 'virtual:mvu-host-bundle'
  const resolvedId = '\0' + virtualId
  return {
    name: 'mvu-host-bundle',
    resolveId(id) { if (id === virtualId) return resolvedId },
    async load(id) {
      if (id !== resolvedId) return
      const { build } = await import('esbuild')
      const entry = fileURLToPath(new URL('./src/mvu/mvu-host-entry.mjs', import.meta.url))
      const result = await build({
        entryPoints: [entry],
        bundle: true,
        format: 'iife',
        platform: 'browser',
        target: 'es2020',
        charset: 'utf8',
        write: false,
        // 绝对 URL（https://jsdelivr…）esbuild 默认视作 external，保留 import() 不打进来。
      })
      return `export default ${JSON.stringify(result.outputFiles[0].text)}`
    },
  }
}

export default defineConfig({
  plugins: [vue(), mvuHostBundlePlugin()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
  },
})
