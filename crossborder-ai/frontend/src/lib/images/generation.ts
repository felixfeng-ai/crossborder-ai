export type ImageGenerationMode =
  | 'product_scene'
  | 'free_creation'
  | 'platform_white'

export type ImageQualityTier = 'fast' | 'standard' | 'hd'
export type ImageGenerationProvider = 'auto' | 'seedream' | 'aliyun' | 'replicate'

export interface ImageGenerationModeOption {
  id: ImageGenerationMode
  label: string
  description: string
}

export interface ImageQualityTierOption {
  id: ImageQualityTier
  label: string
  resolution: string
  description: string
  credits: Record<ImageGenerationMode, number>
}

export interface ImageGenerationDraft {
  mode: ImageGenerationMode
  prompt: string
  referenceAssetIds: string[]
  qualityTier: ImageQualityTier
  aspectRatio?: string
  platformPresetId?: string | null
  negativePrompt?: string
  stylePreset?: string | null
  useBrandPersona?: boolean
  provider?: ImageGenerationProvider
  numOutputs?: number
  campaignId?: string | null
  idempotencyKey?: string
}

export interface ImageGenerationRequest {
  mode: ImageGenerationMode
  prompt: string
  reference_asset_ids: string[]
  quality_tier: ImageQualityTier
  aspect_ratio: string
  platform_preset_id: string | null
  negative_prompt: string
  style_preset: string | null
  use_brand_persona: boolean
  provider: ImageGenerationProvider
  num_outputs: number
  campaign_id: string | null
  idempotency_key?: string
}

export const IMAGE_GENERATION_MODES: ImageGenerationModeOption[] = [
  {
    id: 'product_scene',
    label: '商品场景',
    description: '保持参考商品一致，生成可直接投放的场景图',
  },
  {
    id: 'free_creation',
    label: '自由创作',
    description: '从提示词开始创作广告视觉，不默认注入品牌人设',
  },
  {
    id: 'platform_white',
    label: '平台白底',
    description: '按 Amazon、TikTok Shop 等平台尺寸输出白底商品图',
  },
]

export const IMAGE_QUALITY_TIERS: Record<
  ImageQualityTier,
  ImageQualityTierOption
> = {
  fast: {
    id: 'fast',
    label: '快速',
    resolution: '1024x1024',
    description: '适合草图、构图探索和批量测试',
    credits: {
      free_creation: 3,
      product_scene: 8,
      platform_white: 0,
    },
  },
  standard: {
    id: 'standard',
    label: '标准',
    resolution: '1280x1280',
    description: '质量与速度平衡，适合日常上新',
    credits: {
      free_creation: 5,
      product_scene: 10,
      platform_white: 0,
    },
  },
  hd: {
    id: 'hd',
    label: '高清',
    resolution: '1440x1440',
    description: '适合主图、详情页和高质量素材沉淀',
    credits: {
      free_creation: 8,
      product_scene: 12,
      platform_white: 0,
    },
  },
}

export const IMAGE_ASPECT_RATIOS = ['1:1', '4:5', '3:4', '16:9', '9:16'] as const

export function imageGenerationCredits(
  mode: ImageGenerationMode,
  qualityTier: ImageQualityTier,
  count = 1,
): number {
  const safeCount = Number.isFinite(count) ? Math.max(1, Math.floor(count)) : 1
  return IMAGE_QUALITY_TIERS[qualityTier].credits[mode] * safeCount
}

export function validateImageGeneration(
  draft: Pick<
    ImageGenerationDraft,
    'mode' | 'prompt' | 'referenceAssetIds' | 'qualityTier'
  >,
): string {
  if (draft.mode !== 'platform_white' && !draft.prompt.trim()) {
    return '请输入画面描述'
  }
  if (!(draft.qualityTier in IMAGE_QUALITY_TIERS)) return '请选择有效的质量档位'
  if (draft.mode === 'product_scene') {
    if (draft.referenceAssetIds.length < 1) return '商品场景至少需要 1 张参考图'
    if (draft.referenceAssetIds.length > 4) return '商品场景最多支持 4 张参考图'
  }
  if (draft.mode === 'platform_white' && draft.referenceAssetIds.length < 1) {
    return '平台白底至少需要 1 张商品图'
  }
  return ''
}

export function buildImageGenerationRequest(
  draft: ImageGenerationDraft,
): ImageGenerationRequest {
  return {
    mode: draft.mode,
    prompt: draft.prompt.trim(),
    reference_asset_ids:
      draft.mode === 'free_creation' ? [] : draft.referenceAssetIds,
    quality_tier: draft.qualityTier,
    aspect_ratio: draft.aspectRatio || '1:1',
    platform_preset_id: draft.platformPresetId ?? null,
    negative_prompt: draft.negativePrompt?.trim() || '',
    style_preset: draft.stylePreset ?? null,
    // 自由创作不应被品牌人设污染；需要时由用户显式打开。
    use_brand_persona:
      draft.useBrandPersona ?? draft.mode !== 'free_creation',
    provider: draft.provider || 'auto',
    num_outputs: Math.min(4, Math.max(1, draft.numOutputs || 1)),
    campaign_id: draft.campaignId ?? null,
    idempotency_key: draft.idempotencyKey,
  }
}
