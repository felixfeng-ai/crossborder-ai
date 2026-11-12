import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BarChart3,
  ExternalLink,
  Loader2,
  Send,
  Store,
  TriangleAlert,
} from 'lucide-react'
import apiClient from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type {
  MarketingCopyAsset,
  MarketingCopyResponse,
} from '@/lib/agent/marketingCopy'
import { toErrorMessage } from '@/utils/errorMessage'

interface Channel {
  id: string
  shop_name: string
}

interface CampaignPublication {
  id: string
  platform: string
  status: string
  external_url: string | null
  error: string | null
  created_at: string
}

interface PerformanceResponse {
  totals: {
    impressions: number
    clicks: number
    orders: number
    conversions: number
    spend: number
    revenue: number
    ctr: number
    cvr: number
    roas: number
  }
  currency: string
}

export function MarketingDistributionBoard({
  campaignId,
}: {
  campaignId: string
}) {
  const queryClient = useQueryClient()
  const [channelId, setChannelId] = useState('')
  const [copyId, setCopyId] = useState('')
  const [error, setError] = useState('')
  const [metricForm, setMetricForm] = useState({
    platform: 'tiktok',
    period_start: new Date().toISOString().slice(0, 10),
    period_end: new Date().toISOString().slice(0, 10),
    impressions: '0',
    clicks: '0',
    orders: '0',
    spend: '0',
    revenue: '0',
  })

  const copiesQuery = useQuery<MarketingCopyResponse>({
    queryKey: ['marketing-copy-assets', campaignId],
    queryFn: async () => {
      const response = await apiClient.get(
        `/marketing-campaigns/${campaignId}/copy`,
      )
      return response.data
    },
  })
  const channelsQuery = useQuery<Channel[]>({
    queryKey: ['shopify-channels'],
    queryFn: async () => {
      const response = await apiClient.get('/shopify/channels')
      return response.data || []
    },
  })
  const publicationsQuery = useQuery<{ items: CampaignPublication[] }>({
    queryKey: ['campaign-publications', campaignId],
    queryFn: async () => {
      const response = await apiClient.get(
        `/marketing-campaigns/${campaignId}/publications`,
      )
      return response.data
    },
  })
  const performanceQuery = useQuery<PerformanceResponse>({
    queryKey: ['campaign-performance', campaignId],
    queryFn: async () => {
      const response = await apiClient.get(
        `/marketing-campaigns/${campaignId}/performance`,
      )
      return response.data
    },
  })

  const shopifyCopies = (copiesQuery.data?.items || []).filter(
    (item: MarketingCopyAsset) =>
      item.platform === 'shopify' && item.compliance_status === 'pass',
  )
  const channels = channelsQuery.data || []

  useEffect(() => {
    if (!channelId && channels.length) setChannelId(channels[0].id)
  }, [channelId, channels])
  useEffect(() => {
    if (!copyId && shopifyCopies.length) setCopyId(shopifyCopies[0].id)
  }, [copyId, shopifyCopies])

  const publishMutation = useMutation({
    mutationFn: async (platform: 'shopify' | 'amazon') => {
      const response = await apiClient.post(
        `/marketing-campaigns/${campaignId}/publications`,
        {
          platform,
          copy_id: platform === 'shopify' ? copyId : null,
          channel_id: platform === 'shopify' ? channelId : null,
        },
        { headers: { 'Idempotency-Key': crypto.randomUUID() } },
      )
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['campaign-publications', campaignId],
      })
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '活动发布失败'))
    },
  })

  const metricsMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post(
        `/marketing-campaigns/${campaignId}/metrics`,
        {
          items: [
            {
              platform: metricForm.platform,
              source: 'manual',
              period_start: `${metricForm.period_start}T00:00:00Z`,
              period_end: `${metricForm.period_end}T23:59:59Z`,
              impressions: Number(metricForm.impressions) || 0,
              clicks: Number(metricForm.clicks) || 0,
              orders: Number(metricForm.orders) || 0,
              conversions: Number(metricForm.orders) || 0,
              spend: Number(metricForm.spend) || 0,
              revenue: Number(metricForm.revenue) || 0,
              currency: 'USD',
              metadata: {},
            },
          ],
        },
      )
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['campaign-performance', campaignId],
      })
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '效果数据保存失败'))
    },
  })

  const totals = performanceQuery.data?.totals
  return (
    <div className="mt-2 border border-border bg-background">
      <div className="grid gap-3 border-b border-border p-3 md:grid-cols-2">
        <div className="border border-border p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="flex items-center gap-1.5 text-xs font-medium">
                <Store className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
                Shopify 发布
              </p>
              <p className="mt-1 text-[10px] text-muted-foreground">
                发布为 Shopify 草稿商品
              </p>
            </div>
            <Badge variant={channels.length ? 'secondary' : 'outline'}>
              {channels.length ? '可用' : '未绑定店铺'}
            </Badge>
          </div>
          <div className="mt-3 grid gap-2">
            <select
              aria-label="Shopify 文案"
              value={copyId}
              onChange={(event) => setCopyId(event.target.value)}
              className="h-8 w-full min-w-0 border border-input bg-background px-2 text-xs"
            >
              <option value="">选择 Shopify 文案</option>
              {shopifyCopies.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.variant_key} · {item.headline}
                </option>
              ))}
            </select>
            <select
              aria-label="Shopify 店铺"
              value={channelId}
              onChange={(event) => setChannelId(event.target.value)}
              className="h-8 w-full min-w-0 border border-input bg-background px-2 text-xs"
            >
              <option value="">选择店铺</option>
              {channels.map((channel) => (
                <option key={channel.id} value={channel.id}>
                  {channel.shop_name}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              className="h-8"
              disabled={!copyId || !channelId || publishMutation.isPending}
              onClick={() => publishMutation.mutate('shopify')}
            >
              {publishMutation.isPending ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Send className="mr-1 h-3.5 w-3.5" />
              )}
              发布 Shopify
            </Button>
          </div>
        </div>

        <div className="border border-border p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="flex items-center gap-1.5 text-xs font-medium">
                <TriangleAlert className="h-3.5 w-3.5 text-[color:var(--factory-coral)]" />
                Amazon 发布
              </p>
              <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
                SP-API 已支持授权，Listing 发布尚未接入。
              </p>
            </div>
            <Badge variant="outline">待接入</Badge>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="mt-3 h-8 w-full"
            disabled={publishMutation.isPending}
            onClick={() => publishMutation.mutate('amazon')}
          >
            记录待接入状态
          </Button>
        </div>
      </div>

      <div className="grid gap-4 p-3 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-medium">
            <BarChart3 className="h-3.5 w-3.5" />
            活动效果
          </p>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              ['曝光', totals?.impressions || 0],
              ['点击', totals?.clicks || 0],
              ['订单', totals?.orders || 0],
              ['收入', `${performanceQuery.data?.currency || 'USD'} ${totals?.revenue || 0}`],
              ['CTR', `${totals?.ctr || 0}%`],
              ['CVR', `${totals?.cvr || 0}%`],
              ['ROAS', totals?.roas || 0],
              ['花费', totals?.spend || 0],
            ].map(([label, value]) => (
              <div key={String(label)} className="border border-border bg-[var(--factory-panel)] p-2">
                <p className="text-[9px] text-muted-foreground">{label}</p>
                <p className="metric-number mt-1 text-sm font-medium">{value}</p>
              </div>
            ))}
          </div>

          <div className="mt-3 space-y-2">
            {(publicationsQuery.data?.items || []).slice(0, 5).map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-3 border border-border px-2.5 py-2">
                <div className="min-w-0">
                  <p className="text-[11px] font-medium">{item.platform} 发布</p>
                  <p className="truncate text-[9px] text-muted-foreground">
                    {item.error || item.external_url || item.status}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <Badge variant={item.status === 'completed' ? 'secondary' : 'outline'}>
                    {item.status}
                  </Badge>
                  {item.external_url && (
                    <a
                      href={item.external_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex h-7 w-7 items-center justify-center text-muted-foreground hover:text-foreground"
                      aria-label="打开发布结果"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="border border-border p-3">
          <p className="text-xs font-medium">录入效果数据</p>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <select
              aria-label="效果平台"
              className="col-span-2 h-8 border border-input bg-background px-2 text-xs"
              value={metricForm.platform}
              onChange={(event) => setMetricForm({ ...metricForm, platform: event.target.value })}
            >
              <option value="tiktok">TikTok</option>
              <option value="amazon">Amazon</option>
              <option value="shopify">Shopify</option>
            </select>
            {[
              ['period_start', '开始日期'],
              ['period_end', '结束日期'],
            ].map(([key, label]) => (
              <div key={key} className="space-y-1">
                <Label>{label}</Label>
                <Input
                  type="date"
                  value={metricForm[key as 'period_start' | 'period_end']}
                  className="h-8 text-xs"
                  onChange={(event) => setMetricForm({ ...metricForm, [key]: event.target.value })}
                />
              </div>
            ))}
            {[
              ['impressions', '曝光'],
              ['clicks', '点击'],
              ['orders', '订单'],
              ['spend', '花费'],
              ['revenue', '收入'],
            ].map(([key, label]) => (
              <div key={key} className="space-y-1">
                <Label>{label}</Label>
                <Input
                  type="number"
                  min={0}
                  value={metricForm[key as keyof typeof metricForm]}
                  className="h-8 text-xs"
                  onChange={(event) => setMetricForm({ ...metricForm, [key]: event.target.value })}
                />
              </div>
            ))}
          </div>
          {error && <p className="mt-2 text-[10px] text-destructive">{error}</p>}
          <Button
            size="sm"
            className="mt-3 h-8 w-full"
            disabled={metricsMutation.isPending}
            onClick={() => metricsMutation.mutate()}
          >
            {metricsMutation.isPending && (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            )}
            保存效果数据
          </Button>
        </div>
      </div>
    </div>
  )
}
