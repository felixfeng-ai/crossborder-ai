export interface VideoQualityTier {
  id: string
  name: string
  description: string
  provider: string
  model: string
  resolution: string
  credits_per_second: number
  estimated_time_multiplier: number
}

export interface VideoStylePreset {
  id: string
  name: string
  description: string
  prompt: string
  music: string
}

export const DEFAULT_QUALITY_TIER = 'standard'

export function qualityTierCredits(
  tiers: VideoQualityTier[],
  tierId: string,
  duration: number,
): number {
  const tier = tiers.find((item) => item.id === tierId)
  if (!tier || duration <= 0) return 0
  return Math.max(1, Math.ceil(tier.credits_per_second * duration))
}

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
