import {
  imageGenerationCredits,
  type ImageQualityTier,
} from '@/lib/images/generation'

export type CampaignAssetKind = 'image' | 'video' | 'marketing_video'

export interface CampaignImageVariant {
  asset_id: string
  name: string
  variant_index: number
  thumbnail_url: string
  download_url: string
  created_at: string
}

export interface CampaignAsset {
  id: string
  kind: CampaignAssetKind
  status: string
  prompt: string
  urls: string[]
  thumbnail_url: string | null
  image_asset_id?: string | null
  suite_id?: string | null
  platform?: string | null
  aspect_ratio?: string | null
  variants?: CampaignImageVariant[]
  credits: number
  created_at: string
}

export interface CampaignAssetsResponse {
  counts: {
    images: number
    image_tasks: number
    videos: number
    marketing_videos: number
    total: number
  }
  items: CampaignAsset[]
}

export interface CampaignImageBoardVariant extends CampaignImageVariant {
  task_id: string
  prompt: string
  suite_id?: string | null
  platform?: string | null
}

export type MarketingImageDirection = 'product_hero' | 'lifestyle' | 'ad_creative'

export const BATCH_OUTPUT_OPTIONS = [1, 2, 4] as const
export const MARKETING_IMAGE_CREDITS = 3

export const MARKETING_SUITE_PLATFORMS = [
  { id: 'amazon-main', label: 'Amazon 主图' },
  { id: 'tiktok-main', label: 'TikTok Shop' },
  { id: 'shopify-product', label: 'Shopify 商品图' },
  { id: 'shein-main', label: 'SHEIN 商品图' },
  { id: 'temu-main', label: 'Temu 主图' },
] as const

export const MARKETING_SUITE_DIRECTIONS = [
  { id: 'conversion', label: '转化导向' },
  { id: 'lifestyle', label: '生活场景' },
  { id: 'campaign', label: '活动氛围' },
  { id: 'premium', label: '品牌质感' },
] as const

export const MARKETING_IMAGE_DIRECTIONS: Array<{
  id: MarketingImageDirection
  label: string
}> = [
  { id: 'product_hero', label: '商品主图' },
  { id: 'lifestyle', label: '生活场景' },
  { id: 'ad_creative', label: '广告创意' },
]

const DIRECTION_PROMPTS: Record<MarketingImageDirection, string> = {
  product_hero: '生成高转化商品主图，保留商品外观、材质、Logo 和包装文字',
  lifestyle: '生成真实生活场景营销图，保留商品外观和关键细节',
  ad_creative: '生成适合社交广告的高冲击力营销图，保留商品外观和品牌识别',
}

export const CAMPAIGN_ASSET_LABELS: Record<CampaignAssetKind, string> = {
  image: '图片',
  video: '商品视频',
  marketing_video: '营销成片',
}

export const RUNNING_ASSET_STATUSES = new Set([
  'pending',
  'processing',
  'queued',
  'running',
  'rendering',
])

export function buildMarketingImagePrompt(
  direction: MarketingImageDirection,
  note: string,
): string {
  const detail = note.trim()
  return detail
    ? `${DIRECTION_PROMPTS[direction]}。${detail}`
    : `${DIRECTION_PROMPTS[direction]}。画面真实、主体清晰、适合跨境电商投放`
}

export function estimatedMarketingImageCredits(count: number): number {
  return Math.max(1, Math.min(4, Number(count) || 1)) * MARKETING_IMAGE_CREDITS
}

export function estimatedMarketingSuiteCredits(
  platformIds: string[],
  qualityTier: ImageQualityTier = 'fast',
): number {
  const count = new Set(platformIds.filter(Boolean)).size
  return imageGenerationCredits('product_scene', qualityTier, Math.max(1, count))
}

export function marketingSuitePlatformLabel(platformId: string | null | undefined): string {
  return MARKETING_SUITE_PLATFORMS.find((item) => item.id === platformId)?.label || ''
}

const SUITE_DIRECTION_PROMPTS: Record<string, string> = {
  conversion: '以高转化为目标，突出商品卖点和清晰购买理由',
  lifestyle: '把商品放入真实使用场景，保持生活方式自然可信',
  campaign: '以营销活动为主，画面有明确的节日或活动氛围',
  premium: '以高级品牌质感为主，克制构图、精细光线和材质表现',
}

export function buildMarketingSuitePrompt({
  title,
  direction,
  theme,
  platformLabel,
  note = '',
}: {
  title: string
  direction: string
  theme: string
  platformLabel: string
  note?: string
}): string {
  const parts = [
    `为${platformLabel}生成跨境电商营销图片`,
    `活动主题：${title.trim()}`,
    SUITE_DIRECTION_PROMPTS[direction] || SUITE_DIRECTION_PROMPTS.conversion,
    '严格保持参考商品的外观、材质、Logo、包装文字和颜色一致',
    '商业摄影质感，主体清晰，可直接投放',
  ]
  if (theme.trim()) parts.push(`视觉氛围：${theme.trim()}`)
  if (note.trim()) parts.push(`补充要求：${note.trim()}`)
  return parts.join('。')
}

export function flattenCampaignImageVariants(
  assets: CampaignAsset[],
): CampaignImageBoardVariant[] {
  return assets
    .filter((asset) => asset.kind === 'image')
    .flatMap((asset) =>
      [...(asset.variants || [])]
        .sort((left, right) => left.variant_index - right.variant_index)
        .map((variant) => ({
          ...variant,
          task_id: asset.id,
          prompt: asset.prompt,
          suite_id: asset.suite_id,
          platform: asset.platform,
        })),
    )
}

export function campaignAssetStatusLabel(asset: CampaignAsset): string {
  if (RUNNING_ASSET_STATUSES.has(asset.status)) {
    return `${CAMPAIGN_ASSET_LABELS[asset.kind]}生成中`
  }
  if (['failed', 'canceled'].includes(asset.status)) {
    return '生成失败'
  }
  return CAMPAIGN_ASSET_LABELS[asset.kind]
}
