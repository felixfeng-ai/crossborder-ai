/** 视频模型能力来自后端，前端只负责展示和预算，不自行假设可用性。 */
export interface VideoQualityTier {
  id: string
  name: string
  description: string
  provider: string
  model: string
  resolution: string
  credits_per_second: number
  estimated_time_multiplier: number
  min_duration?: number
  max_duration?: number
  max_reference_images?: number
  supports_audio?: boolean
}

export interface VideoStylePreset {
  id: string
  name: string
  description: string
  prompt: string
  music: string
}

export const DEFAULT_QUALITY_TIER = 'standard'

export type VideoQualityContext = 'marketing' | 'storyboard' | 'single'
export type VideoProvider = 'minimax' | 'jimeng'
export type VideoProviderMode = 'auto' | VideoProvider

const PROVIDER_LABELS: Record<string, string> = {
  minimax: 'MiniMax',
  jimeng: '即梦 Seedance',
}

const PROVIDER_ORDER: VideoProvider[] = ['minimax', 'jimeng']

const RECOMMENDED_TIERS: Record<VideoQualityContext, string[]> = {
  marketing: ['seedance', 'standard', 'draft'],
  storyboard: ['seedance', 'standard', 'draft'],
  single: ['standard', 'draft', 'seedance'],
}

const PROVIDER_DEFAULT_TIERS: Record<VideoProvider, string[]> = {
  minimax: ['standard', 'draft', 'cinematic'],
  jimeng: ['seedance', 'seedance_fast', 'seedance_mini', 'seedance_25'],
}

export function videoProviderLabel(provider: string): string {
  return PROVIDER_LABELS[provider] || provider || '视频供应商'
}

/** 当前配置实际可选的视频供应商，不把未配置的引擎展示给用户。 */
export function availableVideoProviders(
  tiers: VideoQualityTier[],
): VideoProvider[] {
  const configured = new Set(tiers.map((tier) => tier.provider))
  return PROVIDER_ORDER.filter((provider) => configured.has(provider))
}

/** 过滤某个供应商下的全部质量档位。 */
export function tiersForProvider(
  tiers: VideoQualityTier[],
  provider: VideoProvider,
): VideoQualityTier[] {
  return tiers.filter((tier) => tier.provider === provider)
}

/** 优先选择供应商默认档位，再回退到首个可用档位。 */
export function providerDefaultQualityTier(
  tiers: VideoQualityTier[],
  provider: VideoProvider,
): VideoQualityTier | null {
  const candidates = tiersForProvider(tiers, provider)
  for (const tierId of PROVIDER_DEFAULT_TIERS[provider]) {
    const match = candidates.find((tier) => tier.id === tierId)
    if (match) return match
  }
  return candidates[0] || null
}

/** 根据营销、分镜或单镜头场景推荐质量档位。 */
export function recommendedQualityTier(
  tiers: VideoQualityTier[],
  context: VideoQualityContext,
): VideoQualityTier | null {
  for (const tierId of RECOMMENDED_TIERS[context]) {
    const match = tiers.find((tier) => tier.id === tierId)
    if (match) return match
  }
  return tiers[0] || null
}

/** 说明不同视频引擎更适合的画面类型，帮助用户做选择。 */
export function videoProviderHint(provider: string): string {
  if (provider === 'minimax') {
    return '商品结构、多图参考和稳定量产更稳。'
  }
  if (provider === 'jimeng') {
    return '人物动作、镜头运动和生活化营销更自然。'
  }
  return '根据当前创作模式自动匹配视频引擎。'
}

/** 按秒单价计算视频积分，并至少收取 1 积分。 */
export function qualityTierCredits(
  tiers: VideoQualityTier[],
  tierId: string,
  duration: number,
): number {
  const tier = tiers.find((item) => item.id === tierId)
  if (!tier || duration <= 0) return 0
  return Math.max(1, Math.ceil(tier.credits_per_second * duration))
}

/** 档位或风格的兜底名称用于避免空选择器。 */
export function qualityTierLabel(
  tiers: VideoQualityTier[],
  tierId: string,
): string {
  return tiers.find((item) => item.id === tierId)?.name || '未选择'
}

export function stylePresetLabel(
  styles: VideoStylePreset[],
  styleId: string,
): string {
  return styles.find((item) => item.id === styleId)?.name || '默认风格'
}
