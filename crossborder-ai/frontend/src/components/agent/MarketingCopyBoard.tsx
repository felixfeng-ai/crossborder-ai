import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  Copy,
  Languages,
  Loader2,
  Pencil,
  RotateCcw,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import apiClient from '@/api/client'
import ConfirmDialog from '@/components/common/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  MARKETING_COPY_PLATFORMS,
  copyPlatformLabel,
  formatMarketingCopy,
  latestCopyByPlatform,
  performanceStatusLabel,
  type MarketingCopyAsset,
  type MarketingCopyPlatform,
  type MarketingCopyResponse,
} from '@/lib/agent/marketingCopy'
import { toErrorMessage } from '@/utils/errorMessage'

interface MarketingCopyBoardProps {
  campaignId: string
  language: string
  market: string
}

interface EditCopyForm {
  headline: string
  body: string
  cta: string
}

export function MarketingCopyBoard({
  campaignId,
  language,
  market,
}: MarketingCopyBoardProps) {
  const queryClient = useQueryClient()
  const [platform, setPlatform] = useState<MarketingCopyPlatform>('tiktok')
  const [instructions, setInstructions] = useState('')
  const [error, setError] = useState('')
  const [copiedId, setCopiedId] = useState('')
  const [editingCopy, setEditingCopy] = useState<MarketingCopyAsset | null>(null)
  const [editForm, setEditForm] = useState<EditCopyForm>({
    headline: '',
    body: '',
    cta: '',
  })
  const [deleteTarget, setDeleteTarget] = useState<MarketingCopyAsset | null>(null)

  const copyQuery = useQuery<MarketingCopyResponse>({
    queryKey: ['marketing-copy-assets', campaignId],
    queryFn: async () => {
      const response = await apiClient.get(
        `/marketing-campaigns/${campaignId}/copy`,
      )
      return response.data
    },
  })
  const latest = latestCopyByPlatform(copyQuery.data?.items || [])
  const visibleItems = latest[platform]

  const generateMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post(
        `/marketing-campaigns/${campaignId}/copy/generate`,
        {
          platforms: MARKETING_COPY_PLATFORMS,
          language,
          instructions,
        },
      )
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      setInstructions('')
      queryClient.invalidateQueries({
        queryKey: ['marketing-copy-assets', campaignId],
      })
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '营销文案生成失败'))
    },
  })

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!editingCopy) throw new Error('缺少待编辑文案')
      const response = await apiClient.patch(
        `/marketing-campaigns/${campaignId}/copy/${editingCopy.id}`,
        editForm,
      )
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      setEditingCopy(null)
      queryClient.invalidateQueries({
        queryKey: ['marketing-copy-assets', campaignId],
      })
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '文案更新失败'))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (assetId: string) => {
      await apiClient.delete(
        `/marketing-campaigns/${campaignId}/copy/${assetId}`,
      )
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      setDeleteTarget(null)
      queryClient.invalidateQueries({
        queryKey: ['marketing-copy-assets', campaignId],
      })
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '文案删除失败'))
    },
  })

  const resumeMutation = useMutation({
    mutationFn: async (assetId: string) => {
      const response = await apiClient.post(
        `/marketing-campaigns/${campaignId}/copy/${assetId}/resume`,
      )
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['marketing-copy-assets', campaignId],
      })
      queryClient.invalidateQueries({
        queryKey: ['campaign-optimization', campaignId],
      })
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '恢复 A/B 版本失败'))
    },
  })

  const startEditing = (asset: MarketingCopyAsset) => {
    setEditingCopy(asset)
    setEditForm({
      headline: asset.headline,
      body: asset.body,
      cta: asset.cta,
    })
  }

  const copyAsset = async (asset: MarketingCopyAsset) => {
    try {
      await navigator.clipboard.writeText(formatMarketingCopy(asset))
      setCopiedId(asset.id)
      window.setTimeout(() => setCopiedId(''), 1600)
    } catch {
      setError('复制失败，请检查浏览器剪贴板权限')
    }
  }

  return (
    <div className="mt-2 border border-border bg-background">
      <div className="border-b border-border p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="flex items-center gap-1.5 text-xs font-medium">
              <Languages className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
              多平台 A/B 文案
            </p>
            <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
              {market} · {language.toUpperCase()} · 每个平台两个独立购买动机
            </p>
          </div>
          <div className="mt-1 flex w-full min-w-0 flex-col gap-2 sm:mt-0 sm:max-w-xl sm:flex-row">
            <Input
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              maxLength={1000}
              placeholder="补充要求，例如：突出节日礼赠、避免夸张承诺"
              className="h-8 min-w-0 flex-1 text-xs"
              aria-label="文案补充要求"
            />
            <Button
              size="sm"
              className="h-8 w-full shrink-0 gap-1 text-[11px] sm:w-auto"
              disabled={generateMutation.isPending}
              onClick={() => generateMutation.mutate()}
            >
              {generateMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              生成三平台文案
            </Button>
          </div>
        </div>
        {error && <p className="mt-2 text-[11px] text-destructive">{error}</p>}
      </div>

      <div className="flex overflow-x-auto border-b border-border px-3 py-2">
        {MARKETING_COPY_PLATFORMS.map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={platform === item}
            className={`shrink-0 border-b-2 px-3 py-1.5 text-[11px] transition-colors ${
              platform === item
                ? 'border-[var(--factory-accent)] font-medium text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
            onClick={() => setPlatform(item)}
          >
            {copyPlatformLabel(item)}
            <span className="ml-1.5 text-[9px] text-muted-foreground">
              {latest[item].length}
            </span>
          </button>
        ))}
      </div>

      <div className="p-3">
        {copyQuery.isLoading ? (
          <div className="flex min-h-24 items-center justify-center text-xs text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            加载活动文案
          </div>
        ) : visibleItems.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {visibleItems.map((asset) => (
              <CopyCard
                key={asset.id}
                asset={asset}
                editing={editingCopy?.id === asset.id}
                editForm={editForm}
                copied={copiedId === asset.id}
                updating={updateMutation.isPending}
                resuming={
                  resumeMutation.isPending
                  && resumeMutation.variables === asset.id
                }
                onEditFormChange={setEditForm}
                onStartEdit={() => startEditing(asset)}
                onCancelEdit={() => setEditingCopy(null)}
                onSaveEdit={() => updateMutation.mutate()}
                onCopy={() => copyAsset(asset)}
                onDelete={() => setDeleteTarget(asset)}
                onResume={() => resumeMutation.mutate(asset.id)}
              />
            ))}
          </div>
        ) : (
          <div className="flex min-h-24 flex-col items-center justify-center border border-dashed border-border text-center">
            <Languages className="h-5 w-5 text-muted-foreground" />
            <p className="mt-2 text-xs font-medium">
              还没有 {copyPlatformLabel(platform)} 文案
            </p>
            <p className="mt-1 text-[10px] text-muted-foreground">
              生成后会同时创建 A/B 两个版本
            </p>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="删除这条营销文案？"
        description={`将删除 ${deleteTarget ? copyPlatformLabel(deleteTarget.platform) : ''} 的 ${deleteTarget?.variant_key || ''} 版本，此操作不可恢复。`}
        pending={deleteMutation.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget.id)
        }}
      />
    </div>
  )
}

function CopyCard({
  asset,
  editing,
  editForm,
  copied,
  updating,
  resuming,
  onEditFormChange,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onCopy,
  onDelete,
  onResume,
}: {
  asset: MarketingCopyAsset
  editing: boolean
  editForm: EditCopyForm
  copied: boolean
  updating: boolean
  resuming: boolean
  onEditFormChange: (form: EditCopyForm) => void
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: () => void
  onCopy: () => void
  onDelete: () => void
  onResume: () => void
}) {
  const angle = String(asset.metadata.angle || '')
  return (
    <article className="border border-border bg-[var(--factory-panel)] p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary">版本 {asset.variant_key}</Badge>
          <Badge
            variant={
              asset.performance_status === 'paused'
                ? 'destructive'
                : asset.performance_status === 'winner'
                  ? 'secondary'
                  : 'outline'
            }
          >
            {performanceStatusLabel(asset.performance_status)}
          </Badge>
          {angle && <span className="text-[10px] text-muted-foreground">{angle}</span>}
        </div>
        <Badge variant={asset.compliance_status === 'pass' ? 'secondary' : 'destructive'}>
          {asset.compliance_status === 'pass' ? '合规通过' : '需要修改'}
        </Badge>
      </div>

      {editing ? (
        <div className="mt-3 space-y-2">
          <div className="space-y-1">
            <Label htmlFor={`copy-headline-${asset.id}`}>标题</Label>
            <Input
              id={`copy-headline-${asset.id}`}
              value={editForm.headline}
              className="h-8 text-xs"
              onChange={(event) => onEditFormChange({
                ...editForm,
                headline: event.target.value,
              })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`copy-body-${asset.id}`}>正文</Label>
            <textarea
              id={`copy-body-${asset.id}`}
              value={editForm.body}
              className="min-h-28 w-full resize-y border border-input bg-background px-2.5 py-2 text-xs leading-5 outline-none focus:ring-2 focus:ring-ring"
              onChange={(event) => onEditFormChange({
                ...editForm,
                body: event.target.value,
              })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`copy-cta-${asset.id}`}>CTA</Label>
            <Input
              id={`copy-cta-${asset.id}`}
              value={editForm.cta}
              className="h-8 text-xs"
              onChange={(event) => onEditFormChange({
                ...editForm,
                cta: event.target.value,
              })}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onCancelEdit}>
              <X className="mr-1 h-3.5 w-3.5" />
              取消
            </Button>
            <Button
              size="sm"
              onClick={onSaveEdit}
              disabled={
                updating
                || !editForm.headline.trim()
                || !editForm.body.trim()
                || !editForm.cta.trim()
              }
            >
              {updating ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="mr-1 h-3.5 w-3.5" />
              )}
              保存
            </Button>
          </div>
        </div>
      ) : (
        <>
          <h3 className="mt-2 text-sm font-semibold leading-6">{asset.headline}</h3>
          <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-xs leading-5 text-muted-foreground">
            {asset.body}
          </p>
          <p className="mt-2 text-xs font-medium">{asset.cta}</p>
          {asset.last_evaluated_at && (
            <div className="mt-2 grid grid-cols-3 gap-1.5 border border-border px-2 py-1.5 text-[9px] text-muted-foreground">
              <span>CTR {asset.performance_metrics.ctr || 0}%</span>
              <span>CVR {asset.performance_metrics.cvr || 0}%</span>
              <span>ROAS {asset.performance_metrics.roas || 0}</span>
            </div>
          )}
          {asset.hashtags.length > 0 && (
            <p className="mt-2 text-[10px] leading-4 text-muted-foreground">
              {asset.hashtags.join(' ')}
            </p>
          )}
          <div className="mt-3 flex items-center justify-between border-t border-border pt-2">
            <span className="text-[9px] text-muted-foreground">
              v{asset.version} · {asset.model_used || 'AI'}
            </span>
            <div className="flex items-center gap-1">
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8"
                title="复制文案"
                aria-label={`复制 ${asset.platform} ${asset.variant_key} 文案`}
                onClick={onCopy}
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-500" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8"
                title="编辑文案"
                aria-label={`编辑 ${asset.platform} ${asset.variant_key} 文案`}
                onClick={onStartEdit}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8"
                title="删除文案"
                aria-label={`删除 ${asset.platform} ${asset.variant_key} 文案`}
                onClick={onDelete}
              >
                <Trash2 className="h-3.5 w-3.5 text-destructive" />
              </Button>
              {asset.performance_status === 'paused' && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  title="恢复该版本"
                  aria-label={`恢复 ${asset.platform} ${asset.variant_key} 版本`}
                  onClick={onResume}
                  disabled={resuming}
                >
                  {resuming ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RotateCcw className="h-3.5 w-3.5" />
                  )}
                </Button>
              )}
            </div>
          </div>
        </>
      )}
    </article>
  )
}
