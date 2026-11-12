import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Plus, Sparkles, Target } from 'lucide-react'
import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { CampaignAssetsResponse } from '@/lib/agent/campaignAssets'
import { toErrorMessage } from '@/utils/errorMessage'
import { MarketingAssetBoard } from './MarketingAssetBoard'
import { MarketingCopyBoard } from './MarketingCopyBoard'
import { MarketingImageBatchPanel } from './MarketingImageBatchPanel'

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

export function MarketingCampaignBar({
  campaignId,
  onCampaignChange,
}: MarketingCampaignBarProps) {
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)
  const [assetTab, setAssetTab] = useState<'images' | 'copy'>('images')
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
      return items.some((item) =>
        ['pending', 'processing', 'queued', 'running', 'rendering'].includes(item.status)
      )
        ? 5000
        : false
    },
  })

  const selected = campaigns.find((item) => item.id === campaignId)
  const refreshAssets = () => {
    if (campaignId) {
      queryClient.invalidateQueries({
        queryKey: ['marketing-campaign-assets', campaignId],
      })
    }
    queryClient.invalidateQueries({ queryKey: ['image-assets'] })
    queryClient.invalidateQueries({ queryKey: ['image-generation-history'] })
    queryClient.invalidateQueries({ queryKey: ['material-image-assets'] })
    queryClient.invalidateQueries({ queryKey: ['material-image-history'] })
  }
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
            onChange={(event) => {
              setBatchOpen(false)
              setAssetTab('images')
              onCampaignChange(event.target.value)
            }}
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

      {selected && (
        <div className="mt-2 border-t border-border pt-2">
          <div className="flex items-center justify-between gap-2">
            <div
              role="tablist"
              aria-label="活动素材类型"
              className="flex border border-border p-0.5"
            >
              <button
                type="button"
                role="tab"
                aria-selected={assetTab === 'images'}
                className={`px-3 py-1.5 text-[11px] ${
                  assetTab === 'images'
                    ? 'bg-secondary font-medium text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
                onClick={() => setAssetTab('images')}
              >
                图片素材
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={assetTab === 'copy'}
                className={`px-3 py-1.5 text-[11px] ${
                  assetTab === 'copy'
                    ? 'bg-secondary font-medium text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
                onClick={() => {
                  setBatchOpen(false)
                  setAssetTab('copy')
                }}
              >
                文案素材
              </button>
            </div>
            {assetTab === 'images' && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 gap-1 text-[11px]"
                onClick={() => setBatchOpen((current) => !current)}
              >
                <Sparkles className="h-3 w-3" />
                批量生成
              </Button>
            )}
          </div>
          {assetTab === 'images' ? (
            <>
              {batchOpen && (
                <MarketingImageBatchPanel
                  campaignId={campaignId}
                  onCreated={refreshAssets}
                  onClose={() => setBatchOpen(false)}
                />
              )}
              <MarketingAssetBoard assets={assets} onChanged={refreshAssets} />
            </>
          ) : (
            <MarketingCopyBoard
              campaignId={campaignId}
              language={selected.language}
              market={selected.market}
            />
          )}
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
