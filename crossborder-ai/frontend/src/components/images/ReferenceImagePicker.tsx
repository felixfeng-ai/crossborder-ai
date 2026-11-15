import { ImagePlus, Plus } from 'lucide-react'

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
  label = '商品参考图',
  description,
}: {
  assets: WorkbenchAsset[]
  selectedIds: string[]
  onChange: (ids: string[]) => void
  onUpload: () => void
  max?: number
  disabled?: boolean
  label?: string
  description?: string
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
      <div>
        <div className="flex items-center gap-2">
          <p className="text-[13px] font-medium leading-5">{label}</p>
          <span className="metric-number rounded-[4px] border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground">
            {selectedIds.length}/{max}
          </span>
        </div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          {description ||
            `选择 1-${max} 张本人素材，生成时保持商品主体和关键细节一致`}
        </p>
      </div>

      {assets.length ? (
        <div className="mt-3 grid grid-cols-4 gap-2 sm:grid-cols-6 lg:grid-cols-8">
          {assets.map((asset) => {
            const selected = selectedIds.includes(asset.id)
            const selectedIndex = selectedIds.indexOf(asset.id) + 1
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
                    : 'border-border hover:border-[color:var(--factory-line-strong)]',
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
                  <span className="metric-number absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--factory-accent)] text-[11px] font-medium text-[var(--factory-accent-foreground)]">
                    {selectedIndex}
                  </span>
                )}
              </button>
            )
          })}
          {selectedIds.length < max && (
            <button
              type="button"
              onClick={onUpload}
              disabled={disabled}
              className="flex aspect-square flex-col items-center justify-center rounded-md border border-dashed border-border bg-background text-muted-foreground transition-colors hover:border-[color:var(--factory-accent)]/50 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
              aria-label={`添加${label}`}
            >
              <Plus className="h-4 w-4" />
              <span className="mt-1 text-[11px]">添加参考图</span>
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={onUpload}
          disabled={disabled}
          className="mt-3 flex min-h-24 w-full flex-col items-center justify-center rounded-md border border-dashed border-border bg-background px-4 text-center transition-colors hover:border-[color:var(--factory-accent)]/50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ImagePlus className="mb-2 h-5 w-5 text-muted-foreground" />
          <p className="text-xs text-muted-foreground">点击上传第一张商品图</p>
        </button>
      )}
    </div>
  )
}
