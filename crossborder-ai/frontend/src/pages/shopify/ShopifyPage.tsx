import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ShoppingBag, Link, ExternalLink, Plus, AlertCircle, Loader2,
  Package, FileText, RefreshCw, Store,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import apiClient from '@/api/client'
import { toErrorMessage } from '@/utils/errorMessage'
import {
  pickInitialShopifyChannelId,
  resolveShopifyOrderView,
} from '@/lib/shopifyChannelUi'

export default function ShopifyPage() {
  const navigate = useNavigate()
  const [shopName, setShopName] = useState('')
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null)
  const [showConnect, setShowConnect] = useState(false)

  const connectMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/shopify/connect', { shop: shopName.trim() })
      return response.data as { auth_url: string }
    },
    onSuccess: (data) => {
      window.location.href = data.auth_url
    },
  })

  // 已绑定店铺
  const { data: channels } = useQuery({
    queryKey: ['shopify-channels'],
    queryFn: async () => {
      const r = await apiClient.get('/shopify/channels')
      return r.data || []
    },
  })

  useEffect(() => {
    const nextChannel = pickInitialShopifyChannelId(channels, selectedChannel)
    if (nextChannel !== selectedChannel) {
      setSelectedChannel(nextChannel)
    }
    if (channels?.length === 0) {
      setShowConnect(true)
    }
  }, [channels, selectedChannel])

  // 订单列表（选中店铺后拉取）
  const {
    data: orders,
    isLoading: ordersLoading,
    isError: ordersError,
    error: ordersErrorDetail,
    refetch: refetchOrders,
    isFetching: ordersFetching,
    dataUpdatedAt: ordersUpdatedAt,
  } = useQuery({
    queryKey: ['shopify-orders', selectedChannel],
    queryFn: async () => {
      const r = await apiClient.get('/shopify/orders', { params: { channel_id: selectedChannel } })
      return r.data || []
    },
    enabled: !!selectedChannel,
  })
  const orderView = resolveShopifyOrderView({
    selectedChannel,
    isLoading: ordersLoading,
    isError: ordersError,
    orderCount: orders?.length || 0,
  })
  const selectedChannelData = channels?.find((item: any) => item.id === selectedChannel)
  const hasChannels = Boolean(channels?.length)

  const formatPrice = (price: string) => {
    const n = parseFloat(price)
    return isNaN(n) ? price : `$${n.toFixed(2)}`
  }

  const statusBadge = (status: string) => {
    switch (status) {
      case 'paid': return <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-500/20">{status}</Badge>
      case 'pending': return <Badge variant="outline">{status}</Badge>
      case 'refunded': return <Badge variant="destructive">{status}</Badge>
      default: return <Badge variant="secondary">{status}</Badge>
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      {/* 标题 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <ShoppingBag className="h-6 w-6 text-primary" />
            渠道发布
          </h1>
          <p className="text-muted-foreground text-sm">管理 Shopify 店铺连接、订单与发布状态</p>
        </div>
        <Button onClick={() => navigate('/app/content?platform=shopify')}>
          <Plus className="mr-2 h-4 w-4" />
          发布商品
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* 左侧：店铺管理 */}
        <div className="space-y-4 lg:col-span-1">
          {(!hasChannels || showConnect) ? (
            <Card>
              <CardHeader><CardTitle className="text-sm">绑定店铺</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                <div className="flex gap-2">
                  <Input value={shopName} onChange={(e) => setShopName(e.target.value)}
                    placeholder="例如 your-store" className="text-sm" />
                  <Button
                    disabled={!shopName.trim() || connectMutation.isPending}
                    onClick={() => connectMutation.mutate()}
                    size="sm"
                  >
                    {connectMutation.isPending ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Link className="h-4 w-4 mr-1" />}
                    授权
                  </Button>
                </div>
                {hasChannels && (
                  <Button variant="ghost" size="sm" onClick={() => setShowConnect(false)}>
                    取消
                  </Button>
                )}
                {connectMutation.isError && (
                  <p className="text-sm text-destructive flex items-center gap-1">
                    <AlertCircle className="h-4 w-4" />
                    {toErrorMessage(connectMutation.error, '授权发起失败')}
                  </p>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="flex items-center justify-between gap-3 pt-5">
                <div className="flex items-center gap-2 text-sm">
                  <Store className="h-4 w-4 text-primary" />
                  已连接 {channels?.length || 0} 个店铺
                </div>
                <Button variant="outline" size="sm" onClick={() => setShowConnect(true)}>
                  添加店铺
                </Button>
              </CardContent>
            </Card>
          )}

          {/* 已绑定列表 */}
          <Card>
            <CardHeader><CardTitle className="text-sm">已绑定店铺</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {channels?.length > 0 ? channels.map((c: any) => (
                <div
                  key={c.id}
                  className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                    selectedChannel === c.id ? 'border-primary bg-primary/5' : 'hover:bg-muted/50'
                  }`}
                  onClick={() => setSelectedChannel(c.id)}
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">{c.shop_name}</p>
                    <Badge variant="success" className="text-[10px] h-5">已绑定</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{c.domain}</p>
                </div>
              )) : (
                <p className="text-sm text-muted-foreground text-center py-4">暂未绑定店铺</p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* 右侧：订单列表 */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-sm flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  {selectedChannelData ? `${selectedChannelData.shop_name} · 最近订单` : '最近订单'}
                </CardTitle>
                {selectedChannel && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => refetchOrders()}
                    disabled={ordersFetching}
                  >
                    <RefreshCw className={`h-3.5 w-3.5 mr-1 ${ordersFetching ? 'animate-spin' : ''}`} />
                    刷新
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {orderView === 'no-channel' ? (
                <div className="flex flex-col items-center py-8 text-muted-foreground">
                  <ShoppingBag className="h-8 w-8 mb-2 opacity-40" />
                  <p className="text-sm">连接店铺后自动加载订单</p>
                </div>
              ) : orderView === 'loading' ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : orderView === 'error' ? (
                <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-5">
                  <div className="flex items-start gap-2 text-sm text-destructive">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <div className="space-y-2">
                      <p>{toErrorMessage(ordersErrorDetail, '订单加载失败')}</p>
                      {toErrorMessage(ordersErrorDetail, '').includes('受保护客户数据') && (
                        <a
                          className="inline-flex items-center gap-1 text-xs underline underline-offset-2"
                          href="https://shopify.dev/docs/apps/launch/protected-customer-data"
                          target="_blank"
                          rel="noreferrer"
                        >
                          Shopify 权限申请说明
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              ) : orderView === 'ready' ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="pb-2 font-medium">订单号</th>
                        <th className="pb-2 font-medium">金额</th>
                        <th className="pb-2 font-medium">状态</th>
                        <th className="pb-2 font-medium">客户</th>
                        <th className="pb-2 font-medium">时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orders?.map((o: any) => (
                        <tr key={o.id} className="border-b last:border-0 hover:bg-muted/50">
                          <td className="py-3 pr-3">#{o.order_number}</td>
                          <td className="py-3 pr-3 font-medium">{formatPrice(o.total_price)} {o.currency}</td>
                          <td className="py-3 pr-3">{statusBadge(o.financial_status)}</td>
                          <td className="py-3 pr-3 text-muted-foreground text-xs">{o.customer_email || '-'}</td>
                          <td className="py-3 text-xs text-muted-foreground">
                            {o.created_at ? new Date(o.created_at).toLocaleDateString('zh-CN') : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="flex flex-col items-center py-8 text-muted-foreground">
                  <Package className="h-8 w-8 mb-2 opacity-40" />
                  <p className="text-sm">店铺暂无订单</p>
                  <p className="text-xs mt-1">
                    已同步{ordersUpdatedAt ? ` · ${new Date(ordersUpdatedAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}` : ''}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </motion.div>
  )
}
