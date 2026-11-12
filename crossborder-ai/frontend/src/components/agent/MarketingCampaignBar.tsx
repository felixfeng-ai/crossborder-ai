import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Film, Plus, Target } from 'lucide-react'
import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { resolveMediaUrl } from '@/lib/apiUrl'
import { toErrorMessage } from '@/utils/errorMessage'

interface Campaign {
  id: string
  product_id: string | null
  title: string
  objective: string
  platform: string
  market: string
  language: string
  status: string
  budget_credits: number
  spent_credits: number
}

interface Product {
  id: string
  title: string | null
  url: string
}

type CampaignAssetKind = 'image' | 'video' | 'marketing_video'

interface CampaignAsset {
  id: string
  kind: CampaignAssetKind
  status: string
  prompt: string
  urls: string[]
  thumbnail_url: string | null
  credits: number
  created_at: string
}

interface CampaignAssetsResponse {
  counts: {
    images: number
    videos: number
    marketing_videos: number
    total: number
  }
  items: CampaignAsset[]
}

interface MarketingCampaignBarProps {
  campaignId: string
  onCampaignChange: (campaignId: string) => void
}

const OBJECTIVES = [
  { id: 'conversion', label: '促进成交' },
  { id: 'traffic', label: '获取流量' },
  { id: 'launch', label: '新品发布' },
  { id: 'retention', label: '复购召回' },
]

const PLATFORMS = [
  { id: 'tiktok', label: 'TikTok' },
  { id: 'meta', label: 'Meta' },
  { id: 'amazon', label: 'Amazon' },
  { id: 'shopify', label: 'Shopify' },
]

const RUNNING_ASSET_STATUSES = new Set([
  'pending',
  'processing',
  'queued',
  'running',
  'rendering',
])

const ASSET_KIND_LABELS: Record<CampaignAssetKind, string> = {
  image: '图片',
  video: '商品视频',
  marketing_video: '营销成片',
}

function assetStatusLabel(asset: CampaignAsset): string {
  if (RUNNING_ASSET_STATUSES.has(asset.status)) {
    return `${ASSET_KIND_LABELS[asset.kind]}生成中`
  }
  if (['failed', 'canceled'].includes(asset.status)) {
    return '生成失败'
  }
  return ASSET_KIND_LABELS[asset.kind]
}

export function MarketingCampaignBar({
  campaignId,
  onCampaignChange,
}: MarketingCampaignBarProps) {
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    title: '',
    product_id: '',
    objective: 'conversion',
    platform: 'tiktok',
    market: 'US',
    language: 'en',
    budget_credits: '300',
  })

  const { data: campaigns = [] } = useQuery<Campaign[]>({
    queryKey: ['marketing-campaigns'],
    queryFn: async () => {
      const response = await apiClient.get('/marketing-campaigns')
      return response.data.items || []
    },
  })
  const { data: products = [] } = useQuery<Product[]>({
    queryKey: ['marketing-campaign-products'],
    queryFn: async () => {
      const response = await apiClient.get('/products', {
        params: { page: 1, page_size: 50 },
      })
      return response.data.items || []
    },
    enabled: creating,
  })
  const { data: assets } = useQuery<CampaignAssetsResponse>({
    queryKey: ['marketing-campaign-assets', campaignId],
    queryFn: async () => {
      const response = await apiClient.get(
        `/marketing-campaigns/${campaignId}/assets`,
      )
      return response.data
    },
    enabled: Boolean(campaignId),
    refetchInterval: (query) => {
      const items = query.state.data?.items || []
      return items.some((item) => RUNNING_ASSET_STATUSES.has(item.status))
        ? 5000
        : false
    },
  })

  const selected = campaigns.find((item) => item.id === campaignId)
  const createMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/marketing-campaigns', {
        title: form.title.trim(),
        product_id: form.product_id || null,
        objective: form.objective,
        platform: form.platform,
        market: form.market,
        language: form.language,
        budget_credits: Number(form.budget_credits) || 0,
      })
      return response.data as Campaign
    },
    onSuccess: (campaign) => {
      setError('')
      setCreating(false)
      setForm((current) => ({ ...current, title: '', product_id: '' }))
      onCampaignChange(campaign.id)
      queryClient.invalidateQueries({ queryKey: ['marketing-campaigns'] })
    },
    onError: (err) => {
      setError(toErrorMessage(err, '创建营销活动失败'))
    },
  })

  return (
    <div className="border-b px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5 text-xs font-medium">
          <Target className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
          营销活动
        </div>
        <div className="relative min-w-[180px] flex-1 sm:max-w-[280px]">
          <select
            aria-label="选择营销活动"
            value={campaignId}
            onChange={(event) => onCampaignChange(event.target.value)}
            className="h-8 w-full appearance-none border border-input bg-background px-2.5 pr-8 text-[11px] outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">临时对话（不绑定活动）</option>
            {campaigns.map((campaign) => (
              <option key={campaign.id} value={campaign.id}>
                {campaign.title}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-3 w-3 text-muted-foreground" />
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 gap-1 text-[11px]"
          onClick={() => setCreating((current) => !current)}
        >
          <Plus className="h-3 w-3" />
          新建活动
        </Button>
      </div>

      {selected && (
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          {OBJECTIVES.find((item) => item.id === selected.objective)?.label || selected.objective}
          {' · '}
          {PLATFORMS.find((item) => item.id === selected.platform)?.label || selected.platform}
          {' · '}
          {selected.market}
          {' · 预算 '}
          {selected.budget_credits}
          {' 积分 · 已用 '}
          {selected.spent_credits}
        </p>
      )}

      {selected && assets && assets.counts.total > 0 && (
        <div className="mt-2 flex items-center gap-2 overflow-x-auto pb-1">
          <span className="shrink-0 text-[10px] text-muted-foreground">
            活动素材{' '}
            {[
              assets.counts.images > 0 ? `图片 ${assets.counts.images}` : '',
              assets.counts.videos > 0 ? `视频 ${assets.counts.videos}` : '',
              assets.counts.marketing_videos > 0
                ? `成片 ${assets.counts.marketing_videos}`
                : '',
            ].filter(Boolean).join(' · ')}
          </span>
          {assets.items.slice(0, 8).map((asset) => {
            const thumbnailUrl = asset.thumbnail_url
              ? resolveMediaUrl(asset.thumbnail_url)
              : ''
            const isVideo = asset.kind !== 'image'
            return (
              <div
                key={`${asset.kind}-${asset.id}`}
                className="relative flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden border border-border bg-muted"
                title={asset.prompt}
                aria-label={`${ASSET_KIND_LABELS[asset.kind]}：${asset.prompt}`}
              >
                {thumbnailUrl ? (
                  <img
                    src={thumbnailUrl}
                    alt={`${ASSET_KIND_LABELS[asset.kind]}缩略图`}
                    className="h-full w-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <span className="px-1 text-center text-[8px] leading-3 text-muted-foreground">
                    {assetStatusLabel(asset)}
                  </span>
                )}
                {isVideo && (
                  <span className="absolute bottom-0.5 right-0.5 bg-background/85 p-0.5 text-foreground">
                    <Film className="h-2.5 w-2.5" />
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}

      {creating && (
        <div className="mt-2 border border-border bg-background p-3">
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="campaign-title">活动名称</Label>
              <Input
                id="campaign-title"
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
                placeholder="例如：圣诞香薰礼盒转化活动"
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="campaign-product">绑定商品（可选）</Label>
              <select
                id="campaign-product"
                value={form.product_id}
                onChange={(event) => setForm({ ...form, product_id: event.target.value })}
                className="h-8 w-full border border-input bg-background px-2 text-xs"
              >
                <option value="">暂不绑定</option>
                {products.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.title || product.url}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="campaign-objective">营销目标</Label>
              <select
                id="campaign-objective"
                value={form.objective}
                onChange={(event) => setForm({ ...form, objective: event.target.value })}
                className="h-8 w-full border border-input bg-background px-2 text-xs"
              >
                {OBJECTIVES.map((item) => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="campaign-platform">目标平台</Label>
              <select
                id="campaign-platform"
                value={form.platform}
                onChange={(event) => setForm({ ...form, platform: event.target.value })}
                className="h-8 w-full border border-input bg-background px-2 text-xs"
              >
                {PLATFORMS.map((item) => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="campaign-market">市场</Label>
              <Input
                id="campaign-market"
                value={form.market}
                onChange={(event) => setForm({ ...form, market: event.target.value.toUpperCase() })}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="campaign-budget">积分预算</Label>
              <Input
                id="campaign-budget"
                type="number"
                min={0}
                value={form.budget_credits}
                onChange={(event) => setForm({ ...form, budget_credits: event.target.value })}
                className="h-8 text-xs"
              />
            </div>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <Button
              size="sm"
              className="h-8 text-xs"
              disabled={!form.title.trim() || createMutation.isPending}
              onClick={() => createMutation.mutate()}
            >
              {createMutation.isPending ? '创建中...' : '创建并绑定'}
            </Button>
            <p className="text-[10px] text-destructive">{error}</p>
          </div>
        </div>
      )}
    </div>
  )
}
