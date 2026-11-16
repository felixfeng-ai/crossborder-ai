import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('listing compliance actions contract', () => {
  it('offers automatic repair and manual editing with recheck', () => {
    const page = readSource('src/pages/content/ContentPage.tsx')

    expect(page).toContain('/compliance/fix')
    expect(page).toContain('自动修复')
    expect(page).toContain('手动修改')
    expect(page).toContain('保存并复检')
    expect(page).toContain('/compliance')
  })
})
