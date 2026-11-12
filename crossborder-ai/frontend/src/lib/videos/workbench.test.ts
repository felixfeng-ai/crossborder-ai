import { describe, expect, it } from 'vitest'
import {
  estimateVideoCredits,
  getVideoModel,
  isVideoTerminal,
  videoStatusLabel,
  type VideoCapabilities,
} from './workbench'


const capabilities: VideoCapabilities = {
  enabled: true,
  provider: 'minimax',
  default_model: 'MiniMax-H3-Lite',
  default_resolution: '480P',
  models: [
    {
      id: 'MiniMax-H3-Lite',
      min_duration: 4,
      max_duration: 15,
      resolutions: ['480P', '768P'],
      prices_per_second: { '480P': 0.16, '768P': 0.26 },
      credits_per_second: { '480P': 3, '768P': 4.5 },
    },
  ],
  templates: [
    {
      id: 'clean_product',
      name: '纯净商品动态',
      description: '纯净背景',
      prompt_suffix: 'product shot',
    },
  ],
  quality_tiers: [
    {
      id: 'draft',
      name: '快速草稿',
      description: '预览',
      model: 'MiniMax-H3-Lite',
      resolution: '480P',
      credits_per_second: 8,
      estimated_time_multiplier: 0.7,
    },
  ],
  style_presets: [
    {
      id: 'commerce_showcase',
      name: '电商展示',
      description: '清晰展示',
      prompt: 'clean product shot',
      music: 'light rhythm',
    },
  ],
}


describe('video workbench helpers', () => {
  it('读取模型并按最低积分保护估算费用', () => {
    const model = getVideoModel(capabilities, 'MiniMax-H3-Lite')
    expect(model?.resolutions).toEqual(['480P', '768P'])
    expect(estimateVideoCredits(capabilities, 'MiniMax-H3-Lite', '480P', 4)).toBe(12)
    expect(estimateVideoCredits(capabilities, 'MiniMax-H3-Lite', '768P', 6)).toBe(27)
  })

  it('使用中文状态并识别终态', () => {
    expect(videoStatusLabel('queued')).toBe('排队中')
    expect(videoStatusLabel('running')).toBe('生成中')
    expect(videoStatusLabel('succeeded')).toBe('已完成')
    expect(isVideoTerminal('succeeded')).toBe(true)
    expect(isVideoTerminal('running')).toBe(false)
  })
})
