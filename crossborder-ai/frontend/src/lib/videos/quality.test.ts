import { describe, expect, it } from 'vitest'
import {
  availableVideoProviders,
  providerDefaultQualityTier,
  qualityTierCredits,
  qualityTierLabel,
  recommendedQualityTier,
  stylePresetLabel,
  tiersForProvider,
  videoProviderLabel,
  type VideoQualityTier,
  type VideoStylePreset,
} from './quality'

const tiers: VideoQualityTier[] = [
  {
    id: 'standard',
    name: '标准商用',
    description: '768P',
    provider: 'minimax',
    model: 'MiniMax-H3-Highspeed',
    resolution: '768P',
    credits_per_second: 15,
    estimated_time_multiplier: 1,
  },
  {
    id: 'seedance',
    name: 'Seedance 标准商用',
    description: '720P',
    provider: 'jimeng',
    model: 'doubao-seedance-2-0-260128',
    resolution: '720P',
    credits_per_second: 19,
    estimated_time_multiplier: 1.2,
  },
]

const styles: VideoStylePreset[] = [
  {
    id: 'premium_luxury',
    name: '高端静奢',
    description: '柔和侧光',
    prompt: '',
    music: '',
  },
]

describe('video quality helpers', () => {
  it('calculates quality-tier credits from actual seconds', () => {
    expect(qualityTierCredits(tiers, 'standard', 4)).toBe(60)
    expect(qualityTierCredits(tiers, 'missing', 4)).toBe(0)
  })

  it('resolves quality and style labels', () => {
    expect(qualityTierLabel(tiers, 'standard')).toBe('标准商用')
    expect(stylePresetLabel(styles, 'premium_luxury')).toBe('高端静奢')
    expect(stylePresetLabel(styles, 'missing')).toBe('默认风格')
    expect(videoProviderLabel('jimeng')).toBe('即梦 Seedance')
  })

  it('routes each mode to the recommended engine and quality tier', () => {
    expect(availableVideoProviders(tiers)).toEqual(['minimax', 'jimeng'])
    expect(tiersForProvider(tiers, 'jimeng').map((item) => item.id)).toEqual([
      'seedance',
    ])
    expect(recommendedQualityTier(tiers, 'marketing')?.id).toBe('seedance')
    expect(recommendedQualityTier(tiers, 'storyboard')?.id).toBe('seedance')
    expect(recommendedQualityTier(tiers, 'single')?.id).toBe('standard')
    expect(providerDefaultQualityTier(tiers, 'jimeng')?.id).toBe('seedance')
  })
})
