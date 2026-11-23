export type StoreProviderId = 'shopify' | 'amazon' | 'temu'

export interface StoreProvider {
  id: StoreProviderId
  label: string
  description: string
}

const PROVIDERS: StoreProvider[] = [
  {
    id: 'shopify',
    label: 'Shopify',
    description: '连接独立站，读取订单并发布商品草稿。',
  },
  {
    id: 'amazon',
    label: 'Amazon',
    description: '通过 SP-API 授权读取订单并发布 Listing。',
  },
  {
    id: 'temu',
    label: 'Temu',
    description: '连接 Temu 店铺，读取履约和商品状态。',
  },
]

export function supportedStoreProviders(): StoreProvider[] {
  return PROVIDERS
}

export function storePlatformLabel(platform?: string | null): string {
  return (
    PROVIDERS.find((provider) => provider.id === platform)?.label ??
    platform ??
    '未知渠道'
  )
}

export function storeStatusLabel(status?: string | null): string {
  if (status === 'active') return '已连接'
  if (status === 'expired' || status === 'invalid') return '授权异常'
  if (status === 'revoked') return '已解绑'
  return status || '状态未知'
}

export function normalizeShopifyDomain(value: string): string {
  const input = value.trim()
  if (!input) return ''
  const withoutProtocol = input.replace(/^https?:\/\//i, '')
  const host = withoutProtocol.split('/')[0].toLowerCase()
  return host.endsWith('.myshopify.com')
    ? host.slice(0, -'.myshopify.com'.length)
    : host
}
