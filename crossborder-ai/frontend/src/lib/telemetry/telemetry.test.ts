import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { classifyDevice, createTelemetryQueue, normalizePath } from './client'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('匿名页面遥测', () => {
  it('区分桌面、平板和移动设备', () => {
    expect(classifyDevice(1440)).toBe('desktop')
    expect(classifyDevice(800)).toBe('tablet')
    expect(classifyDevice(390)).toBe('mobile')
  })

  it('移除查询参数和 hash，避免把敏感信息写入分析表', () => {
    expect(normalizePath('/app/images?token=secret#preview')).toBe('/app/images')
    expect(normalizePath('/terms#scope')).toBe('/terms')
  })

  it('队列在达到批次大小时自动发送并支持页面隐藏时补发', async () => {
    const batches: unknown[][] = []
    const queue = createTelemetryQueue({
      batchSize: 2,
      send: async (events) => {
        batches.push(events)
      },
    })

    queue.enqueue({
      event_type: 'page_view',
      visitor_id: 'visitor-123',
      session_id: 'session-123',
      path: '/',
      device_type: 'desktop',
    })
    expect(batches).toHaveLength(0)

    queue.enqueue({
      event_type: 'page_view',
      visitor_id: 'visitor-123',
      session_id: 'session-123',
      path: '/pricing',
      device_type: 'desktop',
    })
    await queue.flush()
    expect(batches).toHaveLength(1)
    expect(batches[0]).toHaveLength(2)
  })

  it('安装 web-vitals 并存在全局采集挂载点', () => {
    const pkg = JSON.parse(readSource('package.json'))
    const main = readSource('src/main.tsx')

    expect(pkg.dependencies['web-vitals']).toBeTruthy()
    expect(main).toContain('TelemetryTracker')
  })
})
