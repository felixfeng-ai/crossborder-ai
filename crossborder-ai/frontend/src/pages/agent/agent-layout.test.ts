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
      'w-full min-w-0 mx-auto flex h-full min-h-0 max-w-3xl flex-col overflow-hidden',
    )
    expect(source).toContain(
      'min-w-0 flex-1 max-w-[80%] max-md:max-w-[calc(100%-3rem)]',
    )
    expect(source).toContain('min-h-0 flex-1 overflow-y-auto')
    expect(source).toContain('shrink-0 border-t')
  })

  it('removes the floating-launcher bottom reserve on full agent pages', () => {
    const source = fs.readFileSync(
      path.resolve(
        process.cwd(),
        'src/components/layout/root-layout.tsx',
      ),
      'utf8',
    )

    expect(source).toContain('isAgentFullPage(location.pathname)')
    expect(source).toContain(
      'flex min-h-0 flex-1 flex-col overflow-hidden p-4 pb-4 md:p-6 md:pb-6 lg:p-8 lg:pb-8',
    )
    expect(source).toContain(
      'flex-1 overflow-y-auto p-4 pb-28 md:p-6 md:pb-28 lg:p-8 lg:pb-28',
    )
  })
})
