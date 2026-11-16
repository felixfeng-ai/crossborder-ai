import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('product delete dialog contract', () => {
  it('uses the fixed viewport confirm dialog instead of an inline banner', () => {
    const page = readSource('src/pages/products/ProductsPage.tsx')

    expect(page).toContain("import ConfirmDialog from '@/components/common/ConfirmDialog'")
    expect(page).toContain('<ConfirmDialog')
    expect(page).not.toContain(
      "{confirmDelete && (\n        <Card className={`${confirmDelete === 'all'",
    )
  })

  it('keeps deletion failures visible in the modal', () => {
    const page = readSource('src/pages/products/ProductsPage.tsx')

    expect(page).toContain('deleteError')
    expect(page).toContain("toErrorMessage(error, '删除失败，请稍后重试')")
    expect(page).toContain('pending={isDeleting}')
  })
})
