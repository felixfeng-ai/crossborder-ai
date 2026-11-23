import { describe, expect, it } from 'vitest'

import {
  canReplaceImage,
  imageCategoryLabel,
  normalizeImageCategory,
} from './asset-management'

describe('asset management', () => {
  it('统一图片分类名称并回退未分类', () => {
    expect(imageCategoryLabel('product')).toBe('商品图')
    expect(imageCategoryLabel('scene')).toBe('场景图')
    expect(imageCategoryLabel('photography')).toBe('摄影图')
    expect(imageCategoryLabel('other')).toBe('未分类')
    expect(normalizeImageCategory('unknown')).toBe('other')
  })

  it('只允许受支持的图片格式和大小替换素材', () => {
    expect(
      canReplaceImage({ type: 'image/webp', size: 1024 }),
    ).toBeNull()
    expect(
      canReplaceImage({ type: 'application/pdf', size: 1024 }),
    ).toBe('请选择 JPG、PNG 或 WebP 图片')
    expect(
      canReplaceImage({ type: 'image/png', size: 11 * 1024 * 1024 }),
    ).toBe('图片大小不能超过 10 MB')
  })
})
