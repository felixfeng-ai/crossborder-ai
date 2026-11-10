import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import SafeHtml from './SafeHtml'

describe('SafeHtml', () => {
  it('渲染安全的商品详情标签并移除脚本与事件属性', () => {
    const markup = renderToStaticMarkup(
      <SafeHtml html='<h2>一杯搞定</h2><p onclick="alert(1)">保温杯</p><script>alert(1)</script>' />,
    )

    expect(markup).toMatch(/<h2[^>]*>一杯搞定<\/h2>/)
    expect(markup).toContain('保温杯')
    expect(markup).not.toContain('<script')
    expect(markup).not.toContain('onclick')
    expect(markup).not.toContain('alert(1)')
  })
})
