import { describe, expect, it } from 'vitest'

import {
  buildImageWorkbenchHref,
  imagePromptFromProductTitle,
} from './imageWorkbenchContext'

describe('image workbench product context', () => {
  it('builds an encoded workbench link with product context', () => {
    expect(
      buildImageWorkbenchHref(
        'product-1',
        '圣诞树 & 桌面摆件 #2026',
      ),
    ).toBe(
      '/app/images?product=product-1&title=%E5%9C%A3%E8%AF%9E%E6%A0%91+%26+%E6%A1%8C%E9%9D%A2%E6%91%86%E4%BB%B6+%232026',
    )
  })

  it('uses a trimmed product title as the initial image prompt', () => {
    expect(imagePromptFromProductTitle('  圣诞铁艺桌面摆件  ')).toBe(
      '圣诞铁艺桌面摆件',
    )
    expect(imagePromptFromProductTitle(null)).toBe('')
  })
})
