import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('管理员运营后台契约', () => {
  it('使用独立 /admin 路由和卖家账号反馈路由', () => {
    const app = readSource('src/App.tsx')

    expect(app).toContain('AdminGuard')
    expect(app).toContain('path="/admin"')
    expect(app).toContain('path="overview"')
    expect(app).toContain('path="feedback"')
    expect(app).toContain('path="plans"')
    expect(app).toContain("path=\"feedback\" element={<FeedbackPage />}")
    expect(app).toContain("Navigate to=\"/admin/orders\"")
  })

  it('管理员壳层提供独立的 QueryClientProvider', () => {
    const layout = readSource('src/pages/admin/AdminLayout.tsx')

    expect(layout).toContain('QueryClientProvider')
    expect(layout).toContain('new QueryClient')
  })

  it('管理员布局包含真实运营入口且可回到卖家工作台', () => {
    const layout = readSource('src/pages/admin/AdminLayout.tsx')

    expect(layout).toContain('运营总览')
    expect(layout).toContain('访问分析')
    expect(layout).toContain('页面性能')
    expect(layout).toContain('套餐管理')
    expect(layout).toContain('反馈收件箱')
    expect(layout).toContain('/app/dashboard')
  })

  it('套餐页面支持创建草稿并发布版本', () => {
    const plans = readSource('src/pages/admin/AdminPlansPage.tsx')

    expect(plans).toContain('创建草稿')
    expect(plans).toContain('/versions')
    expect(plans).toContain('/publish')
  })

  it('反馈页面支持状态、优先级和内部备注', () => {
    const feedback = readSource('src/pages/admin/AdminFeedbackPage.tsx')

    expect(feedback).toContain('in_progress')
    expect(feedback).toContain('priority')
    expect(feedback).toContain('内部备注')
  })
})
