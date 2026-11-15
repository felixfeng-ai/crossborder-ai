import { Check, ImagePlus, Upload } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { resolveMediaUrl } from '@/lib/apiUrl'
import type { WorkbenchAsset } from '@/lib/images/workbench'
import { cn } from '@/utils/cn'


export function ReferenceImagePicker({
  assets,
  selectedIds,
  onChange,
  onUpload,
  max = 4,
  disabled = false,
}: {
  assets: WorkbenchAsset[]
  selectedIds: string[]
  onChange: (ids: string[]) => void
  onUpload: () => void
  max?: number
  disabled?: boolean
}) {
  const toggle = (assetId: string) => {
    if (disabled) return
    if (selectedIds.includes(assetId)) {
      onChange(selectedIds.filter((id) => id !== assetId))
      return
    }
    if (selectedIds.length >= max) return
    onChange([...selectedIds, assetId])
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">商品参考图</p>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
            选择 1-{max} 张本人素材，生成时保持商品主体和关键细节一致
          </p>
        </div>
        <span className="metric-number shrink-0 text-[11px] text-muted-foreground">
          {selectedIds.length}/{max}
        </span>
      </div>

      {assets.length ? (
        <div className="mt-3 grid grid-cols-4 gap-2 sm:grid-cols-6 lg:grid-cols-8">
          {assets.map((asset) => {
            const selected = selectedIds.includes(asset.id)
            const disabledByLimit =
              !selected && selectedIds.length >= max
            return (
              <button
                key={asset.id}
                type="button"
                className={cn(
                  'group relative aspect-square overflow-hidden rounded-md border bg-[var(--factory-raised)]',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  selected
                    ? 'border-[color:var(--factory-accent)] ring-1 ring-[color:var(--factory-accent)]'
                    : 'border-border',
                  (disabled || disabledByLimit) && 'cursor-not-allowed opacity-50',
                )}
                title={asset.name}
                aria-label={`${selected ? '取消选择' : '选择'} ${asset.name}`}
                aria-pressed={selected}
                disabled={disabled || disabledByLimit}
                onClick={() => toggle(asset.id)}
              >
                <img
                  src={resolveMediaUrl(asset.image_url)}
                  alt={asset.name}
                  loading="lazy"
                  className="h-full w-full object-contain p-1.5 transition-transform duration-200 group-hover:scale-[1.03]"
                />
                {selected && (
                  <span className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--factory-accent)] text-[var(--factory-accent-foreground)]">
                    <Check className="h-3 w-3" />
                  </span>
                )}
              </button>
            )
          })}
        </div>
      ) : (
        <div className="mt-3 flex min-h-24 flex-col items-center justify-center border border-dashed border-border bg-background px-4 text-center">
          <ImagePlus className="mb-2 h-5 w-5 text-muted-foreground" />
          <p className="text-xs text-muted-foreground">素材库还没有可用的商品图</p>
        </div>
      )}

      <div className="mt-2 flex justify-end">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 text-xs"
          onClick={onUpload}
          disabled={disabled}
        >
          <Upload className="mr-1.5 h-3.5 w-3.5" />
          上传新素材
        </Button>
      </div>
    </div>
  )
}
