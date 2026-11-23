import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('today agent resilience contract', () => {
  it('后台同步失败时保留页面和最近成功数据', () => {
    const page = readSource('src/pages/agent-work/TodayPage.tsx')

    expect(page).toContain('plan.error && !plan.data')
    expect(page).toContain('timeline.error && !timeline.data')
    expect(page).toContain('<SyncNotice')
    expect(page).toContain('Promise.allSettled')
    expect(page).not.toContain('if (error)')
  })

  it('今日页只保留一个主操作并收起全零指标', () => {
    const page = readSource('src/pages/agent-work/TodayPage.tsx')

    expect(page).toContain('metricTotal > 0')
    expect(page).toContain('今天最重要')
    expect(page).toContain('完整对话')
    expect(page).toContain('<CrossSurfaceComposer')
  })
})
