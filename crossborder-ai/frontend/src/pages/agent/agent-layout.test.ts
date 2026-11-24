import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

describe('agent page scroll layout', () => {
  it('keeps the composer fixed and scrolls only the message history', () => {
    const source = fs.readFileSync(
      path.resolve(process.cwd(), 'src/pages/agent/AgentPage.tsx'),
      'utf8',
    )

    expect(source).not.toContain('h-[calc(100vh-6rem)]')
    expect(source).toContain(
      'mx-auto flex h-full min-h-0 max-w-3xl flex-col overflow-hidden',
    )
    expect(source).toContain('min-h-0 flex-1 overflow-y-auto')
    expect(source).toContain('shrink-0 border-t')
  })
})
