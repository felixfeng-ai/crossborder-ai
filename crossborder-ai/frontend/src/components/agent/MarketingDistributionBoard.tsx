import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BarChart3,
  ExternalLink,
  FileUp,
  Loader2,
  RefreshCw,
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

interface AmazonConnection {
  id: string
  platform: string
  account_name: string
  marketplace_id: string | null
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

interface OptimizationResponse {
  variant_analysis: Array<{
    copy_id: string
    platform: string
    variant_key: string
    headline: string
    performance_status: string
    reason: string
    metrics: {
      ctr: number
      cvr: number
      roas: number
      impressions: number
      clicks: number
    }
  }>
  asset_actions: Array<{
    asset_type: string
    title: string
    detail: string
    variant_key: string | null
  }>
  recommendations: Array<{
    code: string
    severity: string
    title: string
    detail: string
    action: string
  }>
}

export function MarketingDistributionBoard({
  campaignId,
}: {
  campaignId: string
}) {
  const queryClient = useQueryClient()
  const [channelId, setChannelId] = useState('')
  const [copyId, setCopyId] = useState('')
  const [amazonConnectionId, setAmazonConnectionId] = useState('')
  const [amazonCopyId, setAmazonCopyId] = useState('')
  const [amazonProductType, setAmazonProductType] = useState('')
  const [amazonPreview, setAmazonPreview] = useState<{
    status: string
    sku: string
    issues: Array<{ severity?: string; message?: string }>
  } | null>(null)
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
  const [manualCopyId, setManualCopyId] = useState('')
  const [importProvider, setImportProvider] = useState('meta_ads')
  const [importCopyId, setImportCopyId] = useState('')
  const [importFileName, setImportFileName] = useState('')
  const [importCsvText, setImportCsvText] = useState('')

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
  const connectionsQuery = useQuery<AmazonConnection[]>({
    queryKey: ['platform-connections'],
    queryFn: async () => {
      const response = await apiClient.get('/platforms/connections')
      return response.data?.connections || []
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
  const optimizationQuery = useQuery<OptimizationResponse>({
    queryKey: ['campaign-optimization', campaignId],
    queryFn: async () => {
      const response = await apiClient.get(
        `/marketing-campaigns/${campaignId}/optimization`,
      )
      return response.data
    },
  })

  const copies = copiesQuery.data?.items || []
  const shopifyCopies = copies.filter(
    (item: MarketingCopyAsset) =>
      item.platform === 'shopify' && item.compliance_status === 'pass',
  )
  const amazonCopies = copies.filter(
    (item) => item.platform === 'amazon' && item.compliance_status === 'pass',
  )
  const channels = channelsQuery.data || []
  const amazonConnections = (connectionsQuery.data || []).filter(
    (item) => item.platform === 'amazon' && item.marketplace_id,
  )
  const importCopyPlatform = {
    amazon_ads: 'amazon',
    tiktok_ads: 'tiktok',
    meta_ads: 'meta',
  }[importProvider]
  const importCopies = copies.filter(
    (item) => item.platform === importCopyPlatform,
  )
  const manualCopies = copies.filter(
    (item) => item.platform === metricForm.platform,
  )

  useEffect(() => {
    if (!channelId && channels.length) setChannelId(channels[0].id)
  }, [channelId, channels])
  useEffect(() => {
    if (!copyId && shopifyCopies.length) setCopyId(shopifyCopies[0].id)
  }, [copyId, shopifyCopies])
  useEffect(() => {
    if (!amazonConnectionId && amazonConnections.length) {
      setAmazonConnectionId(amazonConnections[0].id)
    }
  }, [amazonConnectionId, amazonConnections])
  useEffect(() => {
    if (!amazonCopyId && amazonCopies.length) {
      setAmazonCopyId(amazonCopies[0].id)
    }
  }, [amazonCopyId, amazonCopies])

  const publishMutation = useMutation({
    mutationFn: async ({
      platform,
      preview = false,
    }: {
      platform: 'shopify' | 'amazon'
      preview?: boolean
    }) => {
      const response = await apiClient.post(
        `/marketing-campaigns/${campaignId}/publications`,
        platform === 'shopify'
          ? {
              platform,
              copy_id: copyId,
              channel_id: channelId,
            }
          : {
              platform,
              copy_id: amazonCopyId,
              channel_id: amazonConnectionId,
              product_type: amazonProductType,
              preview,
            },
        { headers: { 'Idempotency-Key': crypto.randomUUID() } },
      )
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: (data, variables) => {
      if (variables.platform === 'amazon' && variables.preview) {
        setAmazonPreview(data)
      }
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
              copy_id: manualCopyId || null,
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
  const syncMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/shopify/sync-operations', null, {
        params: { channel_id: channelId, days: 30 },
      })
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['campaign-performance', campaignId],
      })
      queryClient.invalidateQueries({
        queryKey: ['campaign-optimization', campaignId],
      })
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, 'Shopify 订单效果同步失败'))
    },
  })

  const importMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post(
        `/marketing-campaigns/${campaignId}/metrics/import`,
        {
          provider: importProvider,
          period_start: `${metricForm.period_start}T00:00:00Z`,
          period_end: `${metricForm.period_end}T23:59:59Z`,
          copy_id: importCopyId || null,
          csv_text: importCsvText,
        },
      )
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      setImportFileName('')
      setImportCsvText('')
      queryClient.invalidateQueries({
        queryKey: ['campaign-performance', campaignId],
      })
      queryClient.invalidateQueries({
        queryKey: ['campaign-optimization', campaignId],
      })
      queryClient.invalidateQueries({
        queryKey: ['marketing-copy-assets', campaignId],
      })
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '广告报表导入失败'))
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
              onClick={() => publishMutation.mutate({ platform: 'shopify' })}
            >
              {publishMutation.isPending ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Send className="mr-1 h-3.5 w-3.5" />
              )}
              发布 Shopify
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-8"
              disabled={!channelId || syncMutation.isPending}
              onClick={() => syncMutation.mutate()}
            >
              {syncMutation.isPending ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="mr-1 h-3.5 w-3.5" />
              )}
              同步订单效果
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
                先预览 Amazon 校验问题，再提交 Listings Items。
              </p>
            </div>
            <Badge variant={amazonConnections.length ? 'secondary' : 'outline'}>
              {amazonConnections.length ? 'SP-API' : '未绑定'}
            </Badge>
          </div>
          <div className="mt-3 grid gap-2">
            <select
              aria-label="Amazon 卖家连接"
              value={amazonConnectionId}
              onChange={(event) => setAmazonConnectionId(event.target.value)}
              className="h-8 w-full min-w-0 border border-input bg-background px-2 text-xs"
            >
              <option value="">选择 Amazon 卖家</option>
              {amazonConnections.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.account_name} · {item.marketplace_id}
                </option>
              ))}
            </select>
            <select
              aria-label="Amazon 文案"
              value={amazonCopyId}
              onChange={(event) => setAmazonCopyId(event.target.value)}
              className="h-8 w-full min-w-0 border border-input bg-background px-2 text-xs"
            >
              <option value="">选择 Amazon 文案</option>
              {amazonCopies.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.variant_key} · {item.headline}
                </option>
              ))}
            </select>
            <Input
              value={amazonProductType}
              onChange={(event) => setAmazonProductType(event.target.value)}
              placeholder="Amazon product type，例如 HOME_FRAGRANCE"
              className="h-8 text-xs"
              aria-label="Amazon product type"
            />
            <div className="grid grid-cols-2 gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-8"
                disabled={
                  !amazonCopyId
                  || !amazonConnectionId
                  || !amazonProductType.trim()
                  || publishMutation.isPending
                }
                onClick={() => publishMutation.mutate({
                  platform: 'amazon',
                  preview: true,
                })}
              >
                预览校验
              </Button>
              <Button
                size="sm"
                className="h-8"
                disabled={
                  !amazonCopyId
                  || !amazonConnectionId
                  || !amazonProductType.trim()
                  || publishMutation.isPending
                }
                onClick={() => publishMutation.mutate({
                  platform: 'amazon',
                  preview: false,
                })}
              >
                发布 Amazon
              </Button>
            </div>
            {amazonPreview && (
              <div className="border border-border px-2 py-1.5 text-[9px] leading-4 text-muted-foreground">
                <p className="font-medium text-foreground">
                  {amazonPreview.status} · {amazonPreview.sku}
                </p>
                {amazonPreview.issues.length ? (
                  amazonPreview.issues.slice(0, 3).map((item, index) => (
                    <p key={`${item.message}-${index}`}>
                      {item.severity || 'ERROR'}：{item.message}
                    </p>
                  ))
                ) : (
                  <p>未返回阻断问题</p>
                )}
              </div>
            )}
          </div>
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

          {(optimizationQuery.data?.variant_analysis || []).length > 0 && (
            <div className="mt-3 border border-border">
              <div className="border-b border-border px-2.5 py-2">
                <p className="text-[11px] font-medium">A/B 版本表现</p>
                <p className="mt-0.5 text-[9px] text-muted-foreground">
                  仅样本充足且差距明确时自动暂停
                </p>
              </div>
              <div className="divide-y divide-border">
                {(optimizationQuery.data?.variant_analysis || []).map((item) => (
                  <div
                    key={item.copy_id}
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 px-2.5 py-2"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[10px] font-medium">
                        {item.platform.toUpperCase()} · {item.variant_key}
                      </p>
                      <p className="mt-0.5 truncate text-[9px] text-muted-foreground">
                        CTR {item.metrics.ctr}% · CVR {item.metrics.cvr}% · ROAS{' '}
                        {item.metrics.roas}
                      </p>
                    </div>
                    <Badge
                      variant={
                        item.performance_status === 'paused'
                          ? 'destructive'
                          : item.performance_status === 'winner'
                            ? 'secondary'
                            : 'outline'
                      }
                    >
                      {item.performance_status === 'paused'
                        ? '已暂停'
                        : item.performance_status === 'winner'
                          ? '推荐继续'
                          : '观察中'}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          )}

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
          <div className="mt-4 border-t border-border pt-3">
            <p className="text-xs font-medium">营销优化建议</p>
            <div className="mt-2 space-y-2">
              {(optimizationQuery.data?.asset_actions || []).slice(0, 3).map((item) => (
                <div key={`${item.asset_type}-${item.title}`} className="border border-border px-2.5 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] font-medium">{item.title}</p>
                    <Badge variant="outline">
                      {item.asset_type === 'image'
                        ? '图片'
                        : item.asset_type === 'video'
                          ? '视频'
                          : '文案'}
                    </Badge>
                  </div>
                  <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
                    {item.detail}
                  </p>
                </div>
              ))}
              {(optimizationQuery.data?.recommendations || []).slice(0, 4).map((item) => (
                <div key={item.code} className="border border-border px-2.5 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] font-medium">{item.title}</p>
                    <Badge
                      variant={
                        item.severity === 'danger'
                          ? 'destructive'
                          : item.severity === 'warning'
                            ? 'outline'
                            : 'secondary'
                      }
                    >
                      {item.severity}
                    </Badge>
                  </div>
                  <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
                    {item.detail}
                  </p>
                  <p className="mt-1 text-[10px] leading-4 text-foreground">
                    {item.action}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="border border-border p-3">
          <p className="text-xs font-medium">录入效果数据</p>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <select
              aria-label="效果平台"
              className="col-span-2 h-8 border border-input bg-background px-2 text-xs"
              value={metricForm.platform}
              onChange={(event) => {
                setMetricForm({ ...metricForm, platform: event.target.value })
                setManualCopyId('')
              }}
            >
              <option value="tiktok">TikTok</option>
              <option value="amazon">Amazon</option>
              <option value="shopify">Shopify</option>
            </select>
            <select
              aria-label="手工数据绑定 A/B 文案"
              className="col-span-2 h-8 border border-input bg-background px-2 text-xs"
              value={manualCopyId}
              onChange={(event) => setManualCopyId(event.target.value)}
              disabled={!manualCopies.length}
            >
              <option value="">
                {manualCopies.length ? '不绑定具体 A/B 文案' : '该平台暂无 A/B 文案'}
              </option>
              {manualCopies.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.variant_key} · {item.headline}
                </option>
              ))}
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

          <div className="mt-4 border-t border-border pt-3">
            <p className="flex items-center gap-1.5 text-xs font-medium">
              <FileUp className="h-3.5 w-3.5" />
              导入广告报表
            </p>
            <p className="mt-1 text-[9px] leading-4 text-muted-foreground">
              支持 Amazon Ads、TikTok Ads、Meta Ads 官方 CSV
            </p>
            <div className="mt-2 grid gap-2">
              <select
                aria-label="广告报表平台"
                value={importProvider}
                onChange={(event) => {
                  setImportProvider(event.target.value)
                  setImportCopyId('')
                }}
                className="h-8 border border-input bg-background px-2 text-xs"
              >
                <option value="amazon_ads">Amazon Ads</option>
                <option value="tiktok_ads">TikTok Ads</option>
                <option value="meta_ads">Meta Ads</option>
              </select>
              <select
                aria-label="绑定 A/B 文案"
                value={importCopyId}
                onChange={(event) => setImportCopyId(event.target.value)}
                className="h-8 border border-input bg-background px-2 text-xs"
                disabled={!importCopies.length}
              >
                <option value="">
                  {importCopies.length ? '不绑定具体 A/B 文案' : '该平台暂无 A/B 文案'}
                </option>
                {importCopies.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.variant_key} · {item.headline}
                  </option>
                ))}
              </select>
              <label className="flex h-16 cursor-pointer flex-col items-center justify-center border border-dashed border-border px-2 text-center">
                <span className="text-[10px] font-medium">
                  {importFileName || '选择 CSV 文件'}
                </span>
                <span className="mt-1 text-[9px] text-muted-foreground">
                  最大 2 MB
                </span>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="sr-only"
                  onChange={async (event) => {
                    const file = event.target.files?.[0]
                    if (!file) return
                    if (file.size > 2 * 1024 * 1024) {
                      setError('CSV 文件不能超过 2 MB')
                      return
                    }
                    setImportFileName(file.name)
                    setImportCsvText(await file.text())
                  }}
                />
              </label>
              <Button
                size="sm"
                variant="outline"
                className="h-8 w-full"
                disabled={!importCsvText || importMutation.isPending}
                onClick={() => importMutation.mutate()}
              >
                {importMutation.isPending ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FileUp className="mr-1 h-3.5 w-3.5" />
                )}
                导入并评估 A/B
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
