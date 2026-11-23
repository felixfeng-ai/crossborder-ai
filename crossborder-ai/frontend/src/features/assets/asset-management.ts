export type ImageCategory = 'product' | 'scene' | 'photography' | 'other'

export function normalizeImageCategory(value?: string | null): ImageCategory {
  return value === 'product' ||
    value === 'scene' ||
    value === 'photography' ||
    value === 'other'
    ? value
    : 'other'
}

export function imageCategoryLabel(value?: string | null): string {
  switch (normalizeImageCategory(value)) {
    case 'product':
      return '商品图'
    case 'scene':
      return '场景图'
    case 'photography':
      return '摄影图'
    default:
      return '未分类'
  }
}

export function canReplaceImage(file: {
  type: string
  size: number
}): string | null {
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    return '请选择 JPG、PNG 或 WebP 图片'
  }
  if (file.size > 10 * 1024 * 1024) {
    return '图片大小不能超过 10 MB'
  }
  return null
}
