import { describe, expect, it } from 'vitest'

import { parseListingDescription } from './listingDescription'

describe('parseListingDescription', () => {
  it('从历史 Markdown 结构中拆出简短描述与 HTML 详情', () => {
    const raw = `## 商品标题
**304 不锈钢真空保温杯 500ml**

---

## 简短描述（可放商品页顶部/集合页）
开车通勤、办公室续命、出门随手带，四季都能用。

---

## 商品详情描述（Shopify 富文本/HTML 可用）

\`\`\`html
<h2>一杯搞定通勤和办公</h2>
<p>这只 <strong>500ml 保温杯</strong> 适合日常携带。</p>
<ul><li>304 不锈钢内胆</li><li>真空保温保冷</li></ul>
\`\`\``

    const result = parseListingDescription(raw)

    expect(result.shortDescription).toContain('开车通勤')
    expect(result.detailHtml).toContain('<h2>一杯搞定通勤和办公</h2>')
    expect(result.detailHtml).not.toContain('```')
    expect(result.format).toBe('html')
    expect(result.source).toBe(raw)
  })

  it('没有历史分节时保留完整 Markdown 正文', () => {
    const raw = `## 产品亮点

- 轻量便携
- 一杯两用`

    const result = parseListingDescription(raw)

    expect(result.shortDescription).toBe('')
    expect(result.detailMarkdown).toBe(raw)
    expect(result.detailHtml).toBe('')
    expect(result.format).toBe('markdown')
  })

  it('纯文本详情不会被误判为 HTML 或 Markdown', () => {
    const result = parseListingDescription('A simple insulated bottle for daily commutes.')

    expect(result.detailMarkdown).toBe('A simple insulated bottle for daily commutes.')
    expect(result.detailHtml).toBe('')
    expect(result.format).toBe('plain')
  })
})
