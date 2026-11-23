import { useRef, useState } from 'react'
import {
  AlertCircle,
  ExternalLink,
  Image as ImageIcon,
  Loader2,
  RefreshCw,
  Replace,
  Trash2,
} from 'lucide-react'

import ConfirmDialog from '@/components/common/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  canReplaceImage,
  imageCategoryLabel,
  type ImageCategory,
} from '@/features/assets/asset-management'
import {
  useDeleteWorkspaceImageMutation,
  useReplaceWorkspaceImageMutation,
  useUpdateWorkspaceImageCategoryMutation,
  useWorkspaceImageLibraryQuery,
} from '@/features/assets/workspace-library-queries'
import type { WorkspaceImageAsset } from '@/features/assets/workspace-library-api'
import { useWorkspaceContextStore } from '@/features/workspace-context/workspace-context-store'
import { resolveMediaUrl } from '@/lib/apiUrl'
import { formatFileSize } from '@/lib/images/workbench'

const CATEGORY_FILTERS: Array<{
  id: 'all' | ImageCategory
  label: string
}> = [
  { id: 'all', label: '全部' },
  { id: 'product', label: '商品图' },
  { id: 'scene', label: '场景图' },
  { id: 'photography', label: '摄影图' },
  { id: 'other', label: '未分类' },
]

export function WorkspaceImageLibrary() {
  const workspaceId = useWorkspaceContextStore(
    (state) => state.activeWorkspaceId,
  )
  const query = useWorkspaceImageLibraryQuery(workspaceId)
  const updateCategory = useUpdateWorkspaceImageCategoryMutation(workspaceId)
  const replace = useReplaceWorkspaceImageMutation(workspaceId)
  const remove = useDeleteWorkspaceImageMutation(workspaceId)
  const [filter, setFilter] = useState<'all' | ImageCategory>('all')
  const [selectedId, setSelectedId] = useState('')
  const [deleteTarget, setDeleteTarget] =
    useState<WorkspaceImageAsset | null>(null)
  const [error, setError] = useState('')
  const replaceInput = useRef<HTMLInputElement>(null)
  const assets = query.data ?? []
  const visible =
    filter === 'all'
      ? assets
      : assets.filter((asset) => asset.category === filter)
  const selected =
    visible.find((asset) => asset.id === selectedId) ?? visible[0] ?? null

  const handleReplace = async (file?: File) => {
    if (!selected || !file) return
    const validation = canReplaceImage(file)
    if (validation) {
      setError(validation)
      return
    }
    setError('')
    try {
      await replace.mutateAsync({ assetId: selected.id, file })
    } catch {
      setError('替换失败，原图片没有被删除')
    } finally {
      if (replaceInput.current) replaceInput.current.value = ''
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setError('')
    try {
      await remove.mutateAsync(deleteTarget.id)
      setSelectedId('')
      setDeleteTarget(null)
    } catch {
      setError('删除失败，素材仍然保留')
    }
  }

  if (query.isLoading) {
    return (
      <div className="flex min-h-80 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="m-4 border border-[color:rgba(217,139,112,0.3)] bg-[color:rgba(217,139,112,0.08)] p-5">
        <p className="flex items-center gap-2 text-sm text-[var(--factory-coral)]">
          <AlertCircle className="h-4 w-4" />
          工作区图片库暂时无法同步
        </p>
        <Button
          size="sm"
          variant="outline"
          className="mt-3"
          onClick={() => void query.refetch()}
        >
          <RefreshCw className="mr-2 h-4 w-4" />
          重新加载
        </Button>
      </div>
    )
  }

  return (
    <div className="grid xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="border-b border-border p-4 xl:border-b-0 xl:border-r">
        <div className="mb-4 flex flex-wrap gap-1">
          {CATEGORY_FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setFilter(item.id)}
              className={`h-8 border px-3 text-[11px] ${
                filter === item.id
                  ? 'border-[var(--factory-accent)] bg-[color:color-mix(in_srgb,var(--factory-accent)_10%,transparent)] text-foreground'
                  : 'border-border text-muted-foreground hover:text-foreground'
              }`}
            >
              {item.label}{' '}
              {item.id === 'all'
                ? assets.length
                : assets.filter((asset) => asset.category === item.id).length}
            </button>
          ))}
        </div>

        {visible.length ? (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {visible.map((asset) => (
              <article
                key={asset.id}
                className={`overflow-hidden border bg-background ${
                  selected?.id === asset.id
                    ? 'border-[var(--factory-accent)] ring-1 ring-[var(--factory-accent)]'
                    : 'border-border'
                }`}
              >
                <button
                  type="button"
                  className="block w-full text-left"
                  onClick={() => setSelectedId(asset.id)}
                >
                  <span className="block aspect-square overflow-hidden bg-[var(--factory-raised)]">
                    <img
                      src={resolveMediaUrl(asset.url)}
                      alt={asset.name}
                      className="h-full w-full object-contain p-2"
                    />
                  </span>
                  <span className="block p-2.5">
                    <span className="block truncate text-xs font-medium">
                      {asset.name}
                    </span>
                    <span className="mt-1 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                      <span>{imageCategoryLabel(asset.category)}</span>
                      <span>{formatFileSize(asset.file_size)}</span>
                    </span>
                  </span>
                </button>
              </article>
            ))}
          </div>
        ) : (
          <div className="flex min-h-64 flex-col items-center justify-center border border-dashed border-border">
            <ImageIcon className="h-7 w-7 text-muted-foreground" />
            <p className="mt-3 text-xs text-muted-foreground">
              当前分类还没有图片
            </p>
          </div>
        )}
      </div>

      <aside className="p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="section-title">图片详情</h2>
          {selected && (
            <a
              href={resolveMediaUrl(selected.url)}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 w-8 items-center justify-center text-muted-foreground hover:text-foreground"
              aria-label="打开工作区原图"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          )}
        </div>

        {selected ? (
          <>
            <div className="mt-3 flex min-h-64 items-center justify-center border border-border bg-[var(--factory-raised)]">
              <img
                src={resolveMediaUrl(selected.url)}
                alt={selected.name}
                className="max-h-[420px] w-full object-contain p-3"
              />
            </div>
            <div className="mt-4 space-y-3">
              <div>
                <p className="truncate text-sm font-medium">{selected.name}</p>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {selected.width} × {selected.height} ·{' '}
                  {formatFileSize(selected.file_size)}
                </p>
              </div>
              <label className="block text-xs text-muted-foreground">
                分类
                <select
                  value={selected.category}
                  onChange={(event) => {
                    const category = event.target.value as ImageCategory
                    setError('')
                    void updateCategory
                      .mutateAsync({ assetId: selected.id, category })
                      .catch(() => setError('分类没有保存，已恢复原分类'))
                  }}
                  className="mt-1.5 h-10 w-full border border-border bg-background px-3 text-sm text-foreground"
                >
                  <option value="product">商品图</option>
                  <option value="scene">场景图</option>
                  <option value="photography">摄影图</option>
                  <option value="other">未分类</option>
                </select>
              </label>
              <input
                ref={replaceInput}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(event) => void handleReplace(event.target.files?.[0])}
              />
              <div className="grid grid-cols-2 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={replace.isPending}
                  onClick={() => replaceInput.current?.click()}
                >
                  {replace.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Replace className="mr-2 h-4 w-4" />
                  )}
                  替换图片
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setDeleteTarget(selected)}
                >
                  <Trash2 className="mr-2 h-4 w-4 text-[var(--factory-coral)]" />
                  删除
                </Button>
              </div>
              <p className="text-[11px] leading-5 text-muted-foreground">
                替换失败时旧图片保持不变。分类只影响挑选，不改写历史引用。
              </p>
            </div>
          </>
        ) : (
          <div className="mt-3 flex min-h-64 items-center justify-center border border-dashed border-border text-xs text-muted-foreground">
            选择一张工作区图片
          </div>
        )}

        {error && (
          <p className="mt-3 text-xs leading-5 text-[var(--factory-coral)]">
            {error}
          </p>
        )}
      </aside>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="删除工作区图片？"
        description={`将永久删除“${deleteTarget?.name ?? ''}”，历史任务引用不会同步恢复。`}
        pending={remove.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void handleDelete()}
      />
    </div>
  )
}
