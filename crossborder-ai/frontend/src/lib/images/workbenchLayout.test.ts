import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

function read(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('image workbench production layout contract', () => {
  it('constrains the workbench and keeps copy inside a stable visual gutter', () => {
    const source = read('src/pages/images/ImagesPage.tsx')

    expect(source).toContain('max-w-[1480px]')
    expect(source).toContain(
      'border border-border bg-[var(--factory-panel)] p-5 sm:p-6 lg:p-8',
    )
    expect(source).toContain('variant="outline"')
  })

  it('uses compact mode controls and ordered reference thumbnails', () => {
    const tabs = read('src/components/images/ImageModeTabs.tsx')
    const picker = read('src/components/images/ReferenceImagePicker.tsx')

    expect(tabs).toContain('min-h-[60px]')
    expect(tabs).toContain('bg-background p-1')
    expect(picker).toContain('selectedIds.indexOf(asset.id) + 1')
    expect(picker).toContain('添加参考图')
  })

  it('puts cost inside the primary action and reserves the mobile AI safe area', () => {
    const page = read('src/pages/images/ImagesPage.tsx')
    const editor = read('src/components/images/ImageEditingPanel.tsx')

    expect(page).toContain('生成 {numOutputs} 张')
    expect(page).toContain('{estimatedCredits} 积分')
    expect(page).toContain('pr-20 lg:pr-0')
    expect(editor).toContain('pr-20 lg:pr-0')
  })

  it('records the future compliance agent in the shared todo document', () => {
    const todo = read('../TODO.md')

    expect(todo).toContain('合规 Agent')
    expect(todo).toContain('ComplianceReport')
    expect(todo).toContain('政策 RAG')
  })

  it('shows platform size presets only for white-background processing', () => {
    const page = read('src/pages/images/ImagesPage.tsx')

    expect(page).toContain("mode === 'platform_white' &&")
    expect(page).toContain('平台白底尺寸')
    expect(page).toContain('仅在平台白底模式生效')
  })
})
