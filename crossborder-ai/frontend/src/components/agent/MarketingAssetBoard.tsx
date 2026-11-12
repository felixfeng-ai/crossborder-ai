import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Check,
  Download,
  Film,
  Images,
  Loader2,
  Pencil,
  Trash2,
  X,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import apiClient from '@/api/client'
import ConfirmDialog from '@/components/common/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  CAMPAIGN_ASSET_LABELS,
  campaignAssetStatusLabel,
  flattenCampaignImageVariants,
  type CampaignAsset,
  type CampaignAssetsResponse,
  type CampaignImageBoardVariant,
} from '@/lib/agent/campaignAssets'
import { resolveMediaUrl } from '@/lib/apiUrl'
import { toErrorMessage } from '@/utils/errorMessage'

interface MarketingAssetBoardProps {
  assets?: CampaignAssetsResponse
  onChanged: () => void
}

export function MarketingAssetBoard({
  assets,
  onChanged,
}: MarketingAssetBoardProps) {
  const [editingId, setEditingId] = useState('')
  const [editingName, setEditingName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<CampaignImageBoardVariant | null>(null)
  const [error, setError] = useState('')

  const variants = flattenCampaignImageVariants(assets?.items || [])
  const imageTasksWithoutVariants = (assets?.items || []).filter(
    (asset) => asset.kind === 'image' && !(asset.variants || []).length,
  )
  const otherAssets = (assets?.items || []).filter((asset) => asset.kind !== 'image')

  const renameMutation = useMutation({
    mutationFn: async () => {
      if (!editingId) throw new Error('缺少待重命名素材')
      const response = await apiClient.patch(`/images/assets/${editingId}`, {
        name: editingName,
      })
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      setEditingId('')
      setEditingName('')
      onChanged()
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '素材重命名失败'))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (assetId: string) => {
      await apiClient.delete(`/images/assets/${assetId}`)
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      setDeleteTarget(null)
      onChanged()
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '删除素材失败'))
    },
  })

  return (
    <div className="mt-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <Images className="h-3 w-3" />
          活动素材板
          <span>
            图片 {assets?.counts.images || 0}
            {' · '}
            视频 {(assets?.counts.videos || 0) + (assets?.counts.marketing_videos || 0)}
          </span>
        </div>
        {error && <p className="text-[10px] text-destructive">{error}</p>}
      </div>

      {variants.length || imageTasksWithoutVariants.length || otherAssets.length ? (
        <div className="mt-2 flex gap-2 overflow-x-auto pb-2">
          {variants.map((variant) => (
            <article
              key={variant.asset_id}
              className="w-32 shrink-0 overflow-hidden border border-border bg-background"
            >
              <a
                href={resolveMediaUrl(variant.download_url)}
                target="_blank"
                rel="noreferrer"
                className="block aspect-square bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                title={variant.name}
              >
                <img
                  src={resolveMediaUrl(variant.thumbnail_url)}
                  alt={variant.name}
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              </a>
              {editingId === variant.asset_id ? (
                <form
                  className="space-y-1 p-1.5"
                  onSubmit={(event) => {
                    event.preventDefault()
                    renameMutation.mutate()
                  }}
                >
                  <Input
                    value={editingName}
                    maxLength={255}
                    autoFocus
                    aria-label="素材名称"
                    className="h-7 px-1.5 text-[10px]"
                    onChange={(event) => setEditingName(event.target.value)}
                  />
                  <div className="grid grid-cols-2 gap-1">
                    <Button
                      size="sm"
                      type="submit"
                      className="h-7 px-1 text-[10px]"
                      aria-label="保存素材名称"
                      disabled={!editingName.trim() || renameMutation.isPending}
                    >
                      {renameMutation.isPending ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Check className="h-3 w-3" />
                      )}
                    </Button>
                    <Button
                      size="sm"
                      type="button"
                      variant="outline"
                      className="h-7 px-1"
                      aria-label="取消重命名"
                      onClick={() => setEditingId('')}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </form>
              ) : (
                <>
                  <p className="truncate px-1.5 pt-1.5 text-[10px] font-medium" title={variant.name}>
                    {variant.name}
                  </p>
                  <div className="grid grid-cols-4 p-1">
                    <Link
                      to={`/app/videos?tab=single&source_asset=${variant.asset_id}`}
                      className="inline-flex h-8 items-center justify-center text-muted-foreground hover:bg-accent hover:text-foreground"
                      title="用此图生成视频"
                      aria-label={`用 ${variant.name} 生成视频`}
                    >
                      <Film className="h-3.5 w-3.5" />
                    </Link>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8"
                      title="重命名素材"
                      aria-label={`重命名 ${variant.name}`}
                      onClick={() => {
                        setEditingId(variant.asset_id)
                        setEditingName(variant.name)
                      }}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <a
                      href={resolveMediaUrl(variant.download_url)}
                      download
                      className="inline-flex h-8 items-center justify-center text-muted-foreground hover:bg-accent hover:text-foreground"
                      title="下载素材"
                      aria-label={`下载 ${variant.name}`}
                    >
                      <Download className="h-3.5 w-3.5" />
                    </a>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8"
                      title="删除素材"
                      aria-label={`删除 ${variant.name}`}
                      onClick={() => setDeleteTarget(variant)}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>
                </>
              )}
            </article>
          ))}

          {imageTasksWithoutVariants.map((asset) => (
            <TaskPlaceholder key={asset.id} asset={asset} />
          ))}
          {otherAssets.map((asset) => (
            <VideoAssetCard key={`${asset.kind}-${asset.id}`} asset={asset} />
          ))}
        </div>
      ) : (
        <div className="mt-2 flex min-h-16 items-center justify-center border border-dashed border-border text-[11px] text-muted-foreground">
          暂无活动素材，可从批量生成开始
        </div>
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="删除这个图片变体？"
        description={`将删除“${deleteTarget?.name || ''}”及其本地文件，其他变体不受影响。此操作不可恢复。`}
        pending={deleteMutation.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget.asset_id)
        }}
      />
    </div>
  )
}

function TaskPlaceholder({ asset }: { asset: CampaignAsset }) {
  return (
    <div className="flex aspect-[4/5] w-32 shrink-0 flex-col overflow-hidden border border-border bg-background text-center">
      {asset.thumbnail_url ? (
        <img
          src={resolveMediaUrl(asset.thumbnail_url)}
          alt={asset.prompt}
          className="h-24 w-full object-cover"
          loading="lazy"
        />
      ) : (
        <div className="flex h-24 items-center justify-center">
          {['pending', 'processing'].includes(asset.status) ? (
            <Loader2 className="h-5 w-5 animate-spin text-[var(--factory-accent)]" />
          ) : (
            <Images className="h-5 w-5 text-muted-foreground" />
          )}
        </div>
      )}
      <div className="p-2">
        <p className="text-[10px] font-medium">{campaignAssetStatusLabel(asset)}</p>
        <p className="mt-1 line-clamp-2 text-[9px] leading-3 text-muted-foreground" title={asset.prompt}>
          {asset.prompt}
        </p>
      </div>
    </div>
  )
}

function VideoAssetCard({ asset }: { asset: CampaignAsset }) {
  return (
    <div className="flex aspect-[4/5] w-32 shrink-0 flex-col overflow-hidden border border-border bg-background">
      <div className="relative flex flex-1 items-center justify-center bg-muted">
        {asset.thumbnail_url ? (
          <img
            src={resolveMediaUrl(asset.thumbnail_url)}
            alt={`${CAMPAIGN_ASSET_LABELS[asset.kind]}缩略图`}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <Film className="h-5 w-5 text-muted-foreground" />
        )}
        <span className="absolute bottom-1 right-1 bg-background/85 p-0.5">
          <Film className="h-3 w-3" />
        </span>
      </div>
      <p className="truncate px-1.5 py-1 text-[10px] font-medium" title={asset.prompt}>
        {asset.prompt}
      </p>
    </div>
  )
}
