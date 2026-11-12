export type ProductReferenceRole =
  | 'front'
  | 'back'
  | 'detail'
  | 'package'
  | 'structure'
  | 'logo'
  | 'scale'
  | 'lifestyle'

export interface ProductReferenceInput {
  asset_id: string
  role: ProductReferenceRole
}

export const REFERENCE_ROLE_OPTIONS: Array<{
  value: ProductReferenceRole
  label: string
}> = [
  { value: 'front', label: '正面' },
  { value: 'back', label: '背面' },
  { value: 'detail', label: '细节' },
  { value: 'package', label: '包装' },
  { value: 'structure', label: '结构' },
  { value: 'logo', label: 'LOGO' },
  { value: 'scale', label: '尺寸' },
  { value: 'lifestyle', label: '场景' },
]

const ALLOWED_ROLES = new Set(REFERENCE_ROLE_OPTIONS.map((item) => item.value))

/** 切换商品图片选择，主图和参考图合计最多 9 张。 */
export function toggleReferenceAsset(
  selectedIds: string[],
  assetId: string,
  maxImages = 9,
): string[] {
  if (selectedIds.includes(assetId)) {
    return selectedIds.filter((item) => item !== assetId)
  }
  if (selectedIds.length >= maxImages) return selectedIds
  return [...selectedIds, assetId]
}

/** 构造后端请求；主图单独发送，避免重复出现在参考图列表。 */
export function buildReferenceAssetsPayload(
  primaryAssetId: string,
  selectedIds: string[],
  roleByAsset: Record<string, ProductReferenceRole>,
): ProductReferenceInput[] {
  const seen = new Set<string>([primaryAssetId])
  return selectedIds
    .filter((assetId) => {
      if (!assetId || seen.has(assetId)) return false
      seen.add(assetId)
      return true
    })
    .slice(0, 8)
    .map((assetId) => ({
      asset_id: assetId,
      role: ALLOWED_ROLES.has(roleByAsset[assetId])
        ? roleByAsset[assetId]
        : 'detail',
    }))
}
