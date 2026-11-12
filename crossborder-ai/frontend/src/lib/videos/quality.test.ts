import { describe, expect, it } from 'vitest'
import {
  qualityTierCredits,
  qualityTierLabel,
  stylePresetLabel,
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
  })
})
