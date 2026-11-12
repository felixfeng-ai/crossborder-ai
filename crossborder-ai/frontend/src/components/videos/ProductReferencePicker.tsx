import { Check, Image as ImageIcon, Star } from 'lucide-react'
import { resolveMediaUrl } from '@/lib/apiUrl'
import {
  REFERENCE_ROLE_OPTIONS,
  toggleReferenceAsset,
  type ProductReferenceRole,
} from '@/lib/videos/references'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { cn } from '@/utils/cn'


export interface ProductImageAsset {
  id: string
  name: string
  image_url: string
  width: number
  height: number
}

interface ProductReferencePickerProps {
  assets: ProductImageAsset[]
  selectedIds: string[]
  primaryId: string
  roleByAsset: Record<string, ProductReferenceRole>
  onSelectedIdsChange: (ids: string[]) => void
  onPrimaryIdChange: (id: string) => void
  onRoleChange: (assetId: string, role: ProductReferenceRole) => void
}

/** 商品主图与多参考图选择器；主图和参考图合计最多 9 张。 */
export function ProductReferencePicker({
  assets,
  selectedIds,
  primaryId,
  roleByAsset,
  onSelectedIdsChange,
  onPrimaryIdChange,
  onRoleChange,
}: ProductReferencePickerProps) {
  const selectedAssets = selectedIds
    .map((id) => assets.find((asset) => asset.id === id))
    .filter((asset): asset is ProductImageAsset => Boolean(asset))

  const toggleAsset = (assetId: string) => {
    const nextIds = toggleReferenceAsset(selectedIds, assetId)
    if (nextIds === selectedIds) return
    onSelectedIdsChange(nextIds)
    if (assetId === primaryId && !nextIds.includes(assetId)) {
      onPrimaryIdChange(nextIds[0] || '')
    }
  }

  if (!assets.length) {
    return (
      <a
        href="/app/images"
        className="mt-2 flex min-h-16 items-center justify-center gap-2 border border-dashed border-border text-xs text-muted-foreground hover:text-foreground"
      >
        <ImageIcon className="h-4 w-4" />
        去图片工作台上传商品主图
      </a>
    )
  }

  return (
    <div className="mt-2 space-y-3">
      <div className="max-h-44 overflow-y-auto pr-1">
        <div className="grid grid-cols-5 gap-2">
          {assets.map((asset) => {
            const selected = selectedIds.includes(asset.id)
            const primary = primaryId === asset.id
            return (
              <button
                key={asset.id}
                type="button"
                title={asset.name}
                aria-label={`${selected ? '移除' : '选择'} ${asset.name}`}
                aria-pressed={selected}
                onClick={() => toggleAsset(asset.id)}
                className={cn(
                  'relative aspect-square overflow-hidden border bg-[#d9dad5] transition-colors',
                  selected
                    ? 'border-[color:var(--factory-accent)] ring-1 ring-[color:var(--factory-accent)]'
                    : 'border-border hover:border-[color:var(--factory-ink)]/30',
                )}
              >
                <img
                  src={resolveMediaUrl(asset.image_url)}
                  alt={asset.name}
                  className="h-full w-full object-contain p-1"
                />
                {selected && (
                  <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center bg-[color:var(--factory-accent)] text-white">
                    <Check className="h-2.5 w-2.5" />
                  </span>
                )}
                {primary && (
                  <span className="absolute bottom-1 left-1 flex h-4 w-4 items-center justify-center bg-black/75 text-white">
                    <Star className="h-2.5 w-2.5 fill-current" />
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs">已选 {selectedAssets.length}/9</Label>
        <span className="text-[10px] text-muted-foreground">首张选中的图片默认为主图</span>
      </div>

      {selectedAssets.length > 0 && (
        <div className="space-y-2">
          {selectedAssets.map((asset) => {
            const primary = asset.id === primaryId
            return (
              <div
                key={asset.id}
                className="flex items-center gap-2 border border-border bg-background px-2 py-1.5"
              >
                <img
                  src={resolveMediaUrl(asset.image_url)}
                  alt={asset.name}
                  className="h-8 w-8 shrink-0 object-contain"
                />
                <span className="min-w-0 flex-1 truncate text-[11px]">{asset.name}</span>
                {primary ? (
                  <span className="shrink-0 text-[10px] text-[color:var(--factory-accent)]">
                    主图 · 正面
                  </span>
                ) : (
                  <>
                    <select
                      value={roleByAsset[asset.id] || 'detail'}
                      aria-label={`${asset.name} 用途`}
                      onChange={(event) => {
                        onRoleChange(asset.id, event.target.value as ProductReferenceRole)
                      }}
                      className="h-7 w-[76px] shrink-0 border border-input bg-background px-1 text-[10px] outline-none focus:ring-1 focus:ring-ring"
                    >
                      {REFERENCE_ROLE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-7 shrink-0 px-1.5 text-[10px]"
                      onClick={() => onPrimaryIdChange(asset.id)}
                      title="设为主图"
                    >
                      <Star className="mr-1 h-3 w-3" />
                      主图
                    </Button>
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
