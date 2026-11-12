export type MarketingCopyPlatform = 'tiktok' | 'amazon' | 'shopify'

export interface MarketingCopyAsset {
  id: string
  batch_id: string
  campaign_id: string
  platform: MarketingCopyPlatform
  variant_key: 'A' | 'B'
  language: string
  headline: string
  body: string
  cta: string
  hashtags: string[]
  keywords: string[]
  metadata: Record<string, unknown>
  status: string
  compliance_status: string
  violations: string[]
  source: string
  model_used: string
  version: number
  created_at: string
  updated_at: string
}

export interface MarketingCopyResponse {
  total: number
  items: MarketingCopyAsset[]
}

export const MARKETING_COPY_PLATFORMS: MarketingCopyPlatform[] = [
  'tiktok',
  'amazon',
  'shopify',
]

const PLATFORM_LABELS: Record<MarketingCopyPlatform, string> = {
  tiktok: 'TikTok',
  amazon: 'Amazon',
  shopify: 'Shopify',
}

export function copyPlatformLabel(platform: MarketingCopyPlatform): string {
  return PLATFORM_LABELS[platform]
}

export function latestCopyByPlatform(
  items: MarketingCopyAsset[],
): Record<MarketingCopyPlatform, MarketingCopyAsset[]> {
  const result: Record<MarketingCopyPlatform, MarketingCopyAsset[]> = {
    tiktok: [],
    amazon: [],
    shopify: [],
  }
  for (const platform of MARKETING_COPY_PLATFORMS) {
    const platformItems = items.filter((item) => item.platform === platform)
    if (!platformItems.length) continue
    const latestBatch = platformItems.reduce((latest, item) => {
      if (!latest) return item.batch_id
      return new Date(item.created_at).getTime() > new Date(
        platformItems.find((candidate) => candidate.batch_id === latest)?.created_at || 0,
      ).getTime()
        ? item.batch_id
        : latest
    }, '')
    result[platform] = platformItems
      .filter((item) => item.batch_id === latestBatch)
      .sort((left, right) => left.variant_key.localeCompare(right.variant_key))
  }
  return result
}

export function formatMarketingCopy(asset: MarketingCopyAsset): string {
  const tags = asset.hashtags.length ? `\n\n${asset.hashtags.join(' ')}` : ''
  return `${asset.headline}\n\n${asset.body}\n\n${asset.cta}${tags}`
}
