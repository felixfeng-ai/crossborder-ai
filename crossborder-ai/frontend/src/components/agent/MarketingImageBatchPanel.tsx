import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Images, Loader2, Sparkles, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import apiClient from '@/api/client'
import { ReferenceImagePicker } from '@/components/images/ReferenceImagePicker'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  MARKETING_SUITE_DIRECTIONS,
  MARKETING_SUITE_PLATFORMS,
  estimatedMarketingSuiteCredits,
} from '@/lib/agent/campaignAssets'
import type { WorkbenchAsset } from '@/lib/images/workbench'
import { toErrorMessage } from '@/utils/errorMessage'

interface MarketingImageBatchPanelProps {
  campaignId: string
  onCreated: () => void
  onClose: () => void
}

export function MarketingImageBatchPanel({
  campaignId,
  onCreated,
  onClose,
}: MarketingImageBatchPanelProps) {
  const navigate = useNavigate()
  const initializedReferences = useRef(false)
  const [title, setTitle] = useState('多平台营销套图')
  const [platforms, setPlatforms] = useState<string[]>([
    'amazon-main',
    'tiktok-main',
    'shopify-product',
  ])
  const [direction, setDirection] = useState('conversion')
  const [theme, setTheme] = useState('')
  const [note, setNote] = useState('')
  const [referenceIds, setReferenceIds] = useState<string[]>([])
  const [error, setError] = useState('')

  const assetsQuery = useQuery<WorkbenchAsset[]>({
    queryKey: ['marketing-suite-reference-assets'],
    queryFn: async () => {
      const response = await apiClient.get('/images/assets')
      return response.data.items || []
    },
  })

  const referenceAssets = (assetsQuery.data || []).filter(
    (asset) => asset.kind !== 'processed' || asset.source_asset_id,
  )
  const estimatedCredits = estimatedMarketingSuiteCredits(platforms, 'fast')

  useEffect(() => {
    if (
      initializedReferences.current ||
      referenceIds.length > 0 ||
      referenceAssets.length === 0
    ) {
      return
    }
    initializedReferences.current = true
    setReferenceIds([referenceAssets[0].id])
  }, [referenceAssets, referenceIds.length])

  const createMutation = useMutation({
    mutationFn: async () => {
      if (platforms.length < 2) throw new Error('至少选择两个平台')
      if (!title.trim()) throw new Error('请输入套图名称')
      if (!referenceIds.length) throw new Error('请选择商品参考图')
      const response = await apiClient.post(
        '/images/marketing-suites',
        {
          campaign_id: campaignId,
          title: title.trim(),
          direction,
          theme: theme.trim(),
          platforms,
          reference_asset_ids: referenceIds,
          quality_tier: 'fast',
          note: note.trim(),
          idempotency_key: crypto.randomUUID(),
        },
      )
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      onCreated()
      onClose()
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '营销套图创建失败'))
    },
  })

  const togglePlatform = (platformId: string) => {
    setPlatforms((current) => (
      current.includes(platformId)
        ? current.filter((item) => item !== platformId)
        : [...current, platformId]
    ))
  }

  return (
    <div className="mt-2 border border-border bg-background p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-medium">
            <Sparkles className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
            生成多平台营销套图
          </p>
          <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
            同一件商品一次生成多个平台版本，单平台失败不会影响其他平台。
          </p>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="h-8 w-8 shrink-0"
          aria-label="关闭批量生成"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="marketing-suite-title">套图名称</Label>
          <Input
            id="marketing-suite-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={255}
            className="h-9 text-xs"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="marketing-suite-direction">营销方向</Label>
          <select
            id="marketing-suite-direction"
            value={direction}
            onChange={(event) => setDirection(event.target.value)}
            className="h-9 w-full border border-input bg-background px-2.5 text-xs outline-none focus:ring-2 focus:ring-ring"
          >
            {MARKETING_SUITE_DIRECTIONS.map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        <div className="flex items-center justify-between gap-3">
          <Label>目标平台</Label>
          <span className="metric-number text-[11px] text-muted-foreground">
            {platforms.length} 个平台
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {MARKETING_SUITE_PLATFORMS.map((platform) => {
            const active = platforms.includes(platform.id)
            return (
              <button
                key={platform.id}
                type="button"
                aria-pressed={active}
                onClick={() => togglePlatform(platform.id)}
                className={`flex h-9 items-center justify-start border px-2.5 text-left text-[11px] transition-colors ${
                  active
                    ? 'border-[color:var(--factory-accent)] bg-[color:var(--factory-accent)]/8 font-medium'
                    : 'border-border text-muted-foreground hover:bg-accent'
                }`}
              >
                {platform.label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="marketing-suite-theme">活动/视觉主题</Label>
          <Input
            id="marketing-suite-theme"
            value={theme}
            onChange={(event) => setTheme(event.target.value)}
            placeholder="例如：圣诞暖光、黑五、夏日海岛"
            className="h-9 text-xs"
            maxLength={80}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="marketing-suite-note">补充要求</Label>
          <Input
            id="marketing-suite-note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="例如：Logo 必须清晰，包装文字不要变形"
            className="h-9 text-xs"
            maxLength={800}
          />
        </div>
      </div>

      <div className="mt-3 border-t border-border pt-3">
        <ReferenceImagePicker
          assets={referenceAssets}
          selectedIds={referenceIds}
          onChange={setReferenceIds}
          onUpload={() => navigate('/app/images')}
          max={4}
          disabled={createMutation.isPending}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Images className="h-3.5 w-3.5" />
          预计 {estimatedCredits} 积分
        </div>
        <div className="flex items-center gap-2">
          {error && <span className="text-[11px] text-destructive">{error}</span>}
          <Button
            type="button"
            size="sm"
            disabled={
              createMutation.isPending ||
              platforms.length < 2 ||
              referenceIds.length < 1 ||
              !title.trim()
            }
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            )}
            {createMutation.isPending
              ? '创建套图中...'
              : `生成 ${platforms.length} 个平台`}
          </Button>
        </div>
      </div>
    </div>
  )
}
