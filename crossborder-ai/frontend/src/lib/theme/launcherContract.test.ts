import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('AI launcher final contract', () => {
  it('uses the platform-native circular launcher with visible text', () => {
    const sidecar = readSource('src/components/agent/AgentSidecar.tsx')

    expect(sidecar).toContain('问 AI')
    expect(sidecar).toContain('rounded-full')
    expect(sidecar).toContain('h-[72px] w-[72px]')
    expect(sidecar).toContain('lg:h-[78px] lg:w-[78px]')
    expect(sidecar).toContain('border-[var(--factory-accent)]')
    expect(sidecar).toContain('bg-[var(--factory-panel)]')
    expect(sidecar).not.toContain(
      'absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[var(--factory-mint)]',
    )
  })

  it('uses a friendly robot instead of the platform V mark', () => {
    const mark = readSource('src/components/brand/AssistantMark.tsx')

    expect(mark).toContain('viewBox="0 0 24 24"')
    expect(mark).toContain('stroke="currentColor"')
    expect(mark).not.toContain('M39 49 64 91 89 49')
  })
})
