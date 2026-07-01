import { describe, expect, it } from 'vitest'

import { renderMarkdown } from '../markdown'

describe('renderMarkdown', () => {
  it('renders fenced HTML fragments inside details as sanitized HTML, not code', () => {
    const html = renderMarkdown(`
<details>
<summary>详细信息</summary>

\`\`\`
<summary style="cursor: pointer;">
  <span class="mvu-avatar">头像</span>
</summary>
\`\`\`
</details>
`)

    expect(html).toContain('<details>')
    expect(html).toContain('<summary>详细信息</summary>')
    expect(html).toContain('<span class="mvu-avatar">头像</span>')
    expect(html).not.toContain('<pre>')
    expect(html).not.toContain('&lt;summary')
  })
})
