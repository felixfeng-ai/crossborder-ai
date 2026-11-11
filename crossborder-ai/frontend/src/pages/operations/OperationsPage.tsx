import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Activity,
  AlertTriangle,
  Bell,
  CheckCircle2,
  CloudDownload,
  Clock3,
  Gauge,
  Loader2,
  PackageCheck,
  RefreshCw,
  Save,
  Settings2,
  TriangleAlert,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import apiClient from '@/api/client'
import {
  formatCoverage,
  operationStatusLabel,
  toMonitorSettingsPayload,
  type MonitorSettings,
  type MonitorSettingsForm,
  type ReplenishmentItem,
} from '@/lib/operations/operations'
import { toErrorMessage } from '@/utils/errorMessage'

interface ScanResult {
  sku_count: number
  low_stock_count: number
  low_margin_count: number
  reorder_count: number
  open_alerts: number
  items: ReplenishmentItem[]
  settings: MonitorSettings
}

interface OperationAlert {
  id: string
  product_id: string | null
  variant_id: string | null
  sku: string | null
  alert_type: string
  severity: 'info' | 'warning' | 'error' | 'critical'
  title: string
  message: string
  status: string
  created_at: string
}

interface Overview {
  settings: MonitorSettings
  open_alerts: number
  last_scanned_at: string | null
}

interface ShopifySyncChannel {
  id: string
  shop_name: string
  shop_domain: string
  is_active: boolean
}

const EMPTY_SETTINGS: MonitorSettingsForm = {
  target_margin_rate: '25',
  low_stock_days: '7',
  lead_time_days: '14',
  safety_stock_days: '3',
  platform_fee_percent: '15',
  shipping_cost: '0',
  cost_increase_alert_rate: '8',
}

export default function OperationsPage() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState('replenishment')
  const [showSettings, setShowSettings] = useState(false)
  const [settingsForm, setSettingsForm] = useState<MonitorSettingsForm>(EMPTY_SETTINGS)
  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [actionError, setActionError] = useState('')
  const [syncMessage, setSyncMessage] = useState('')
  const [savedRateId, setSavedRateId] = useState('')
  const [syncChannelId, setSyncChannelId] = useState('')

  const overviewQuery = useQuery<Overview>({
    queryKey: ['operations-overview'],
    queryFn: async () => {
      const response = await apiClient.get('/operations/overview')
      return response.data
    },
  })

  const alertsQuery = useQuery<{ items: OperationAlert[]; total: number }>({
    queryKey: ['operations-alerts'],
    queryFn: async () => {
      const response = await apiClient.get('/operations/alerts', {
        params: { status: 'open' },
      })
      return response.data
    },
  })

  const shopifyChannelsQuery = useQuery<ShopifySyncChannel[]>({
    queryKey: ['operations-shopify-channels'],
    queryFn: async () => {
      const response = await apiClient.get('/shopify/channels')
      return response.data || []
    },
  })

  useEffect(() => {
    if (!syncChannelId && shopifyChannelsQuery.data?.length) {
      setSyncChannelId(shopifyChannelsQuery.data[0].id)
    }
  }, [shopifyChannelsQuery.data, syncChannelId])

  useEffect(() => {
    const settings = overviewQuery.data?.settings
    if (!settings) return
    setSettingsForm({
      target_margin_rate: String(settings.target_margin_rate),
      low_stock_days: String(settings.low_stock_days),
      lead_time_days: String(settings.lead_time_days),
      safety_stock_days: String(settings.safety_stock_days),
      platform_fee_percent: String(Math.round(settings.platform_fee_rate * 10000) / 100),
      shipping_cost: String(settings.shipping_cost),
      cost_increase_alert_rate: String(settings.cost_increase_alert_rate),
    })
  }, [overviewQuery.data?.settings])

  const scanMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post<ScanResult>('/operations/scan')
      return response.data
    },
    onMutate: () => setActionError(''),
    onSuccess: (data) => {
      setScanResult(data)
      queryClient.invalidateQueries({ queryKey: ['operations-alerts'] })
      queryClient.invalidateQueries({ queryKey: ['operations-overview'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '运营扫描失败')),
  })

  const refreshCostsMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/operations/refresh-costs')
      return response.data as { refreshed: number; failed: number; total: number }
    },
    onMutate: () => {
      setActionError('')
      setSyncMessage('')
    },
    onSuccess: (data) => {
      setSyncMessage(
        `已同步 ${data.refreshed} 个商品供货价${data.failed ? `，${data.failed} 个失败` : ''}`,
      )
      scanMutation.mutate()
    },
    onError: (error) => setActionError(toErrorMessage(error, '供货价同步失败')),
  })

  const syncShopifyMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/shopify/sync-operations', null, {
        params: { channel_id: syncChannelId, days: 30 },
      })
      return response.data as {
        orders_scanned: number
        products_scanned: number
        sales_rate_updates: number
        stock_updates: number
        unmatched_skus: string[]
      }
    },
    onMutate: () => {
      setActionError('')
      setSyncMessage('')
    },
    onSuccess: (data) => {
      const unmatched = data.unmatched_skus.length
        ? `，${data.unmatched_skus.length} 个 SKU 未匹配`
        : ''
      setSyncMessage(
        `Shopify 同步完成：${data.orders_scanned} 个订单，`
        + `${data.sales_rate_updates} 个销量更新，`
        + `${data.stock_updates} 个库存更新${unmatched}`,
      )
      scanMutation.mutate()
    },
    onError: (error) => setActionError(toErrorMessage(error, 'Shopify 数据同步失败')),
  })

  const saveSettingsMutation = useMutation({
    mutationFn: async () => {
      const payload = toMonitorSettingsPayload(settingsForm)
      const response = await apiClient.put('/operations/settings', payload)
      return response.data as MonitorSettings
    },
    onMutate: () => setActionError(''),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['operations-overview'] })
      setShowSettings(false)
    },
    onError: (error) => setActionError(toErrorMessage(error, '监控设置保存失败')),
  })

  const salesRateMutation = useMutation({
    mutationFn: async ({ variantId, rate }: { variantId: string; rate: number }) => {
      const response = await apiClient.patch(
        `/operations/variants/${variantId}/sales-rate`,
        { daily_sales_rate: rate },
      )
      return response.data
    },
    onSuccess: (_, variables) => {
      setSavedRateId(variables.variantId)
      window.setTimeout(() => setSavedRateId(''), 1500)
      scanMutation.mutate()
    },
    onError: (error) => setActionError(toErrorMessage(error, '日均销量保存失败')),
  })

  const acknowledgeMutation = useMutation({
    mutationFn: async (alertId: string) => {
      const response = await apiClient.patch(`/operations/alerts/${alertId}`, {
        status: 'acknowledged',
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['operations-alerts'] })
      queryClient.invalidateQueries({ queryKey: ['operations-overview'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '预警确认失败')),
  })

  const summary = scanResult || {
    sku_count: 0,
    low_stock_count: 0,
    low_margin_count: 0,
    reorder_count: 0,
    open_alerts: alertsQuery.data?.total || overviewQuery.data?.open_alerts || 0,
  }

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Activity className="h-6 w-6 text-primary" />
            运营监控与补货
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            按 SKU 跟踪毛利、库存覆盖、补货点和异常预警。系统每天 02:45 自动扫描。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select
            value={syncChannelId}
            onChange={(event) => setSyncChannelId(event.target.value)}
            className="h-10 min-w-40 rounded-md border border-input bg-background px-3 text-sm"
            aria-label="选择 Shopify 同步店铺"
          >
            <option value="">选择 Shopify 店铺</option>
            {(shopifyChannelsQuery.data || []).map((channel) => (
              <option key={channel.id} value={channel.id}>
                {channel.shop_name}
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            onClick={() => syncShopifyMutation.mutate()}
            disabled={!syncChannelId || syncShopifyMutation.isPending}
          >
            {syncShopifyMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            {syncShopifyMutation.isPending ? '同步中...' : '同步 Shopify 数据'}
          </Button>
          <Button
            variant="outline"
            onClick={() => refreshCostsMutation.mutate()}
            disabled={refreshCostsMutation.isPending}
          >
            {refreshCostsMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <CloudDownload className="mr-2 h-4 w-4" />
            )}
            同步供货价
          </Button>
          <Button variant="outline" onClick={() => setShowSettings((value) => !value)}>
            <Settings2 className="mr-2 h-4 w-4" />
            监控设置
          </Button>
          <Button onClick={() => scanMutation.mutate()} disabled={scanMutation.isPending}>
            {scanMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            {scanMutation.isPending ? '扫描中...' : '运行扫描'}
          </Button>
        </div>
      </div>

      {actionError && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {actionError}
        </div>
      )}

      {syncMessage && (
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-500">
          {syncMessage}
        </div>
      )}

      {showSettings && (
        <Card className="border-primary/20 bg-primary/5">
          <CardHeader>
            <CardTitle className="text-sm">监控阈值</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
              <SettingInput
                label="目标毛利率 %"
                value={settingsForm.target_margin_rate}
                onChange={(value) => setSettingsForm({ ...settingsForm, target_margin_rate: value })}
              />
              <SettingInput
                label="低库存天数"
                value={settingsForm.low_stock_days}
                onChange={(value) => setSettingsForm({ ...settingsForm, low_stock_days: value })}
              />
              <SettingInput
                label="备货周期（天）"
                value={settingsForm.lead_time_days}
                onChange={(value) => setSettingsForm({ ...settingsForm, lead_time_days: value })}
              />
              <SettingInput
                label="安全库存（天）"
                value={settingsForm.safety_stock_days}
                onChange={(value) => setSettingsForm({ ...settingsForm, safety_stock_days: value })}
              />
              <SettingInput
                label="平台费率 %"
                value={settingsForm.platform_fee_percent}
                onChange={(value) => setSettingsForm({ ...settingsForm, platform_fee_percent: value })}
              />
              <SettingInput
                label="单件运费 ¥"
                value={settingsForm.shipping_cost}
                onChange={(value) => setSettingsForm({ ...settingsForm, shipping_cost: value })}
              />
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-48">
                <SettingInput
                  label="成本上涨预警 %"
                  value={settingsForm.cost_increase_alert_rate}
                  onChange={(value) => setSettingsForm({ ...settingsForm, cost_increase_alert_rate: value })}
                />
              </div>
              <Button onClick={() => saveSettingsMutation.mutate()} disabled={saveSettingsMutation.isPending}>
                {saveSettingsMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                保存设置
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="监控 SKU" value={summary.sku_count} icon={Gauge} />
        <Metric label="需要补货" value={summary.reorder_count} icon={PackageCheck} tone={summary.reorder_count ? 'warning' : 'default'} />
        <Metric label="低毛利 SKU" value={summary.low_margin_count} icon={TriangleAlert} tone={summary.low_margin_count ? 'warning' : 'default'} />
        <Metric label="待处理预警" value={summary.open_alerts} icon={Bell} tone={summary.open_alerts ? 'danger' : 'default'} />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="replenishment">补货计划</TabsTrigger>
          <TabsTrigger value="alerts">预警 {alertsQuery.data?.total ? `(${alertsQuery.data.total})` : ''}</TabsTrigger>
        </TabsList>

        <TabsContent value="replenishment">
          <Card>
            <CardHeader className="border-b border-border">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-sm">SKU 补货计划</CardTitle>
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock3 className="h-3.5 w-3.5" />
                  最近扫描：{overviewQuery.data?.last_scanned_at || '尚未扫描'}
                </p>
              </div>
            </CardHeader>
            <CardContent>
              {scanResult ? (
                scanResult.items.length > 0 ? (
                  <div className="space-y-3">
                    <div className="hidden overflow-x-auto md:block">
                      <table className="w-full min-w-[980px] text-left text-sm">
                        <thead className="border-b text-xs text-muted-foreground">
                          <tr>
                            <th className="py-2 font-medium">商品 / SKU</th>
                            <th className="py-2 font-medium">售价 / 成本</th>
                            <th className="py-2 font-medium">毛利</th>
                            <th className="py-2 font-medium">库存</th>
                            <th className="py-2 font-medium">日均销量</th>
                            <th className="py-2 font-medium">覆盖天数</th>
                            <th className="py-2 font-medium">补货点</th>
                            <th className="py-2 font-medium">建议补货</th>
                            <th className="py-2 font-medium">状态</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {scanResult.items.map((item) => (
                            <tr key={item.variant_id}>
                              <td className="max-w-[250px] py-3 pr-3">
                                <p className="truncate text-xs text-muted-foreground">{item.product_title}</p>
                                <p className="font-mono text-xs font-medium">{item.sku}</p>
                              </td>
                              <td className="metric-number py-3 pr-3 text-xs">
                                <p>{item.selling_price == null ? '-' : `¥${item.selling_price}`}</p>
                                <p className="text-muted-foreground">{item.cost_price == null ? '-' : `成本 ¥${item.cost_price}`}</p>
                              </td>
                              <td className={`metric-number py-3 pr-3 text-xs ${item.margin_rate != null && item.margin_rate < 25 ? 'text-[var(--factory-coral)]' : 'text-emerald-500'}`}>
                                {item.margin_rate == null ? '-' : `${item.margin_rate.toFixed(1)}%`}
                              </td>
                              <td className={`metric-number py-3 pr-3 text-xs ${item.stock_quantity < 10 ? 'text-[var(--factory-coral)]' : ''}`}>
                                {item.stock_quantity}
                              </td>
                              <td className="py-3 pr-3">
                                <SalesRateEditor
                                  item={item}
                                  saving={salesRateMutation.isPending}
                                  saved={savedRateId === item.variant_id}
                                  onSave={(rate) => salesRateMutation.mutate({ variantId: item.variant_id, rate })}
                                />
                              </td>
                              <td className="metric-number py-3 pr-3 text-xs">{formatCoverage(item.days_cover)}</td>
                              <td className="metric-number py-3 pr-3 text-xs">{item.reorder_point ?? '-'}</td>
                              <td className="metric-number py-3 pr-3 text-sm font-semibold">{item.suggested_quantity || '-'}</td>
                              <td className="py-3">
                                <StatusBadge status={item.status} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="space-y-2 md:hidden">
                      {scanResult.items.map((item) => (
                        <div key={item.variant_id} className="rounded-md border p-3 space-y-3">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-xs text-muted-foreground">{item.product_title}</p>
                              <p className="font-mono text-xs font-medium">{item.sku}</p>
                            </div>
                            <StatusBadge status={item.status} />
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-xs">
                            <span>库存 {item.stock_quantity}</span>
                            <span>覆盖 {formatCoverage(item.days_cover)}</span>
                            <span>补货点 {item.reorder_point ?? '-'}</span>
                            <span>建议补货 {item.suggested_quantity || '-'}</span>
                            <span>毛利 {item.margin_rate == null ? '-' : `${item.margin_rate.toFixed(1)}%`}</span>
                          </div>
                          <SalesRateEditor
                            item={item}
                            saving={salesRateMutation.isPending}
                            saved={savedRateId === item.variant_id}
                            onSave={(rate) => salesRateMutation.mutate({ variantId: item.variant_id, rate })}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <EmptyState title="暂无 SKU" detail="先在 SKU 中心创建变体后再运行扫描。" />
                )
              ) : (
                <EmptyState title="运行一次运营扫描" detail="扫描后会生成补货建议和预警。" onAction={() => scanMutation.mutate()} />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="alerts">
          <Card>
            <CardHeader className="border-b border-border">
              <CardTitle className="text-sm">待处理预警</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {alertsQuery.data?.items?.length ? (
                alertsQuery.data.items.map((alert) => (
                  <div key={alert.id} className="flex flex-wrap items-start gap-3 rounded-md border px-3 py-3">
                    <SeverityIcon severity={alert.severity} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-medium">{alert.title}</p>
                        {alert.sku && <Badge variant="outline" className="font-mono text-[10px]">{alert.sku}</Badge>}
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">{alert.message}</p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={acknowledgeMutation.isPending}
                      onClick={() => acknowledgeMutation.mutate(alert.id)}
                    >
                      确认
                    </Button>
                  </div>
                ))
              ) : (
                <EmptyState title="暂无待处理预警" detail="运行扫描后，异常会集中出现在这里。" />
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </motion.div>
  )
}

function Metric({
  label,
  value,
  icon: Icon,
  tone = 'default',
}: {
  label: string
  value: number
  icon: typeof Gauge
  tone?: 'default' | 'warning' | 'danger'
}) {
  const color =
    tone === 'danger'
      ? 'text-[var(--factory-coral)]'
      : tone === 'warning'
        ? 'text-[var(--factory-accent)]'
        : 'text-foreground'
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <p className={`metric-number mt-1 text-xl font-semibold ${color}`}>{value}</p>
    </div>
  )
}

function SettingInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input type="number" min="0" value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  )
}

function SalesRateEditor({
  item,
  saving,
  saved,
  onSave,
}: {
  item: ReplenishmentItem
  saving: boolean
  saved: boolean
  onSave: (rate: number) => void
}) {
  const [value, setValue] = useState(String(item.daily_sales_rate))
  useEffect(() => {
    setValue(String(item.daily_sales_rate))
  }, [item.daily_sales_rate])
  const rate = Number(value)
  return (
    <div className="flex items-center gap-1">
      <Input
        type="number"
        min="0"
        step="0.1"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        className="h-8 w-20"
        aria-label={`${item.sku} 日均销量`}
      />
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        disabled={saving || !Number.isFinite(rate) || rate < 0}
        title="保存日均销量"
        aria-label="保存日均销量"
        onClick={() => onSave(rate)}
      >
        {saved ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /> : <Save className="h-3.5 w-3.5" />}
      </Button>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const variant =
    status === 'healthy'
      ? 'success'
      : status === 'out_of_stock'
        ? 'destructive'
        : status === 'reorder'
          ? 'warning'
          : 'outline'
  return <Badge variant={variant as 'success' | 'destructive' | 'warning' | 'outline'}>{operationStatusLabel(status)}</Badge>
}

function SeverityIcon({ severity }: { severity: string }) {
  if (severity === 'critical') return <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
  if (severity === 'error') return <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
  if (severity === 'warning') return <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
  return <Bell className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
}

function EmptyState({
  title,
  detail,
  onAction,
}: {
  title: string
  detail: string
  onAction?: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      <Activity className="mb-3 h-10 w-10 text-muted-foreground/40" />
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
      {onAction && (
        <Button className="mt-4" size="sm" onClick={onAction}>
          <RefreshCw className="mr-2 h-4 w-4" />
          运行扫描
        </Button>
      )}
    </div>
  )
}
