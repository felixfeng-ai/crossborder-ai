import { useState } from 'react'
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Loader2,
  PackageCheck,
  RefreshCw,
  ShoppingBag,
  Store,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  useCommerceStoresQuery,
  useConnectStoreMutation,
} from '@/features/stores/queries'
import {
  normalizeShopifyDomain,
  storePlatformLabel,
  storeStatusLabel,
  supportedStoreProviders,
} from '@/features/stores/stores'
import { useWorkspaceContextStore } from '@/features/workspace-context/workspace-context-store'

const PROVIDER_ICONS = {
  shopify: ShoppingBag,
  amazon: PackageCheck,
  temu: Store,
} as const

export default function StoresPage() {
  const navigate = useNavigate()
  const workspaceId = useWorkspaceContextStore(
    (state) => state.activeWorkspaceId,
  )
  const stores = useCommerceStoresQuery(workspaceId)
  const connect = useConnectStoreMutation(workspaceId)
  const [shopDomain, setShopDomain] = useState('')
  const [shopifyOpen, setShopifyOpen] = useState(false)
  const [error, setError] = useState('')
  const connected = stores.data ?? []

  const connectProvider = async (provider: 'shopify' | 'amazon' | 'temu') => {
    setError('')
    if (provider === 'shopify' && !shopifyOpen) {
      setShopifyOpen(true)
      return
    }
    const shop =
      provider === 'shopify' ? normalizeShopifyDomain(shopDomain) : undefined
    if (provider === 'shopify' && !shop) {
      setError('请输入 Shopify 店铺名称或完整域名')
      return
    }
    try {
      const url = await connect.mutateAsync({ provider, shop })
      window.location.href = url
    } catch {
      setError('没有发起店铺授权，请检查服务商配置后重试')
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6" data-store-management="true">
      <header className="flex flex-col justify-between gap-4 border-b border-border pb-6 sm:flex-row sm:items-end">
        <div>
          <h1 className="page-title">店铺与渠道</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Shopify、Amazon 和 Temu 使用同一工作区权限。连接状态与 App 保持一致。
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={stores.isFetching}
            onClick={() => void stores.refetch()}
          >
            <RefreshCw
              className={`mr-2 h-4 w-4 ${stores.isFetching ? 'animate-spin' : ''}`}
            />
            刷新
          </Button>
          <Button onClick={() => navigate('/app/shopify')}>
            <ArrowRight className="mr-2 h-4 w-4" />
            订单与发布
          </Button>
        </div>
      </header>

      {stores.isError ? (
        <div className="border border-[color:rgba(217,139,112,0.3)] bg-[color:rgba(217,139,112,0.08)] p-5">
          <p className="flex items-center gap-2 text-sm text-[var(--factory-coral)]">
            <AlertCircle className="h-4 w-4" />
            店铺暂时无法同步
          </p>
          <Button
            className="mt-3"
            size="sm"
            variant="outline"
            onClick={() => void stores.refetch()}
          >
            重新加载
          </Button>
        </div>
      ) : stores.isLoading ? (
        <div className="flex min-h-56 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-[var(--factory-accent)]" />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {supportedStoreProviders().map((provider) => {
            const Icon = PROVIDER_ICONS[provider.id]
            const providerStores = connected.filter(
              (item) => item.channel_type === provider.id,
            )
            return (
              <section
                key={provider.id}
                className="border border-border bg-[var(--factory-panel)]"
              >
                <header className="border-b border-border p-4">
                  <div className="flex items-center justify-between gap-3">
                    <Icon className="h-5 w-5 text-[var(--factory-accent)]" />
                    <Badge
                      variant={providerStores.length ? 'success' : 'outline'}
                    >
                      {providerStores.length} 个
                    </Badge>
                  </div>
                  <h2 className="mt-3 text-base font-semibold">{provider.label}</h2>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    {provider.description}
                  </p>
                </header>
                <div className="min-h-28 p-4">
                  {providerStores.length ? (
                    providerStores.map((item) => (
                      <div
                        key={`${item.channel_type}:${item.channel_id}`}
                        className="border-b border-border py-2.5 last:border-b-0"
                      >
                        <p className="truncate text-sm font-medium">{item.name}</p>
                        <p
                          className={`mt-1 flex items-center gap-1.5 text-[11px] ${
                            item.status === 'active'
                              ? 'text-[var(--factory-mint)]'
                              : 'text-[var(--factory-coral)]'
                          }`}
                        >
                          {item.status === 'active' ? (
                            <CheckCircle2 className="h-3 w-3" />
                          ) : (
                            <AlertCircle className="h-3 w-3" />
                          )}
                          {storeStatusLabel(item.status)}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="py-5 text-xs text-muted-foreground">
                      还没有连接 {provider.label}
                    </p>
                  )}
                </div>
                <div className="border-t border-border p-4">
                  {provider.id === 'shopify' && shopifyOpen && (
                    <Input
                      value={shopDomain}
                      onChange={(event) => setShopDomain(event.target.value)}
                      placeholder="demo-store 或完整域名"
                      className="mb-2 h-9 text-xs"
                    />
                  )}
                  <Button
                    className="w-full"
                    size="sm"
                    variant={providerStores.length ? 'outline' : 'default'}
                    disabled={connect.isPending}
                    onClick={() => void connectProvider(provider.id)}
                  >
                    {connect.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    {providerStores.length ? '添加或重新授权' : `连接 ${storePlatformLabel(provider.id)}`}
                  </Button>
                </div>
              </section>
            )
          })}
        </div>
      )}

      {error && (
        <p className="text-sm text-[var(--factory-coral)]">{error}</p>
      )}
    </div>
  )
}
