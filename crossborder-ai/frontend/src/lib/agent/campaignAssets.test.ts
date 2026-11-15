import { describe, expect, it } from 'vitest'

import {
  buildMarketingImagePrompt,
  buildMarketingSuitePrompt,
  estimatedMarketingImageCredits,
  estimatedMarketingSuiteCredits,
  flattenCampaignImageVariants,
  marketingSuitePlatformLabel,
  MARKETING_SUITE_PLATFORMS,
  MARKETING_SUITE_DIRECTIONS,
  type CampaignAsset,
} from './campaignAssets'

describe('marketing campaign asset helpers', () => {
  it('按方向和补充说明生成批量图片提示词', () => {
    const prompt = buildMarketingImagePrompt(
      'lifestyle',
      '冬日客厅，暖光，商品保持清晰',
    )

    expect(prompt).toContain('真实生活场景')
    expect(prompt).toContain('冬日客厅')
    expect(prompt).toContain('保留商品外观')
  })

  it('按图片张数计算营销图片积分', () => {
    expect(estimatedMarketingImageCredits(1)).toBe(3)
    expect(estimatedMarketingImageCredits(4)).toBe(12)
  })

  it('按平台数量计算多平台套图积分', () => {
    expect(MARKETING_SUITE_PLATFORMS.map((item) => item.id)).toEqual(
      expect.arrayContaining(['amazon-main', 'tiktok-main', 'shopify-product']),
    )
    expect(
      estimatedMarketingSuiteCredits(
        ['amazon-main', 'tiktok-main', 'shopify-product'],
        'fast',
      ),
    ).toBe(24)
    expect(MARKETING_SUITE_DIRECTIONS.map((item) => item.id)).toContain(
      'campaign',
    )
    expect(marketingSuitePlatformLabel('amazon-main')).toBe('Amazon 主图')
  })

  it('套图提示词同时包含活动主题和平台要求', () => {
    const prompt = buildMarketingSuitePrompt({
      title: '圣诞香薰礼盒',
      direction: 'campaign',
      theme: '冬季暖光',
      platformLabel: 'Amazon 主图',
      note: '保留包装文字',
    })

    expect(prompt).toContain('圣诞香薰礼盒')
    expect(prompt).toContain('冬季暖光')
    expect(prompt).toContain('Amazon 主图')
    expect(prompt).toContain('保留包装文字')
  })

  it('把多张活动图片展开成独立变体', () => {
    const assets: CampaignAsset[] = [
      {
        id: 'task-1',
        kind: 'image',
        status: 'completed',
        prompt: '节日主图',
        urls: [],
        thumbnail_url: '/api/v1/images/assets/a/file',
        image_asset_id: 'a',
        credits: 6,
        created_at: '2026-11-13T01:00:00Z',
        variants: [
          {
            asset_id: 'a',
            name: '暖光版本',
            variant_index: 0,
            thumbnail_url: '/api/v1/images/assets/a/file',
            download_url: '/api/v1/images/assets/a/file',
            created_at: '2026-11-13T01:00:00Z',
          },
          {
            asset_id: 'b',
            name: '冷光版本',
            variant_index: 1,
            thumbnail_url: '/api/v1/images/assets/b/file',
            download_url: '/api/v1/images/assets/b/file',
            created_at: '2026-11-13T01:01:00Z',
          },
        ],
      },
    ]

    const variants = flattenCampaignImageVariants(assets)

    expect(variants).toHaveLength(2)
    expect(variants.map((item) => item.asset_id)).toEqual(['a', 'b'])
    expect(variants[1].prompt).toBe('节日主图')
  })

  it('展开套图变体时保留平台和套图标识', () => {
    const assets: CampaignAsset[] = [
      {
        id: 'task-suite',
        kind: 'image',
        status: 'completed',
        prompt: '套图平台任务',
        urls: [],
        thumbnail_url: '/api/v1/images/assets/suite/file',
        image_asset_id: 'suite',
        suite_id: 'suite-1',
        platform: 'amazon-main',
        credits: 8,
        created_at: '2026-11-14T01:00:00Z',
        variants: [
          {
            asset_id: 'suite',
            name: 'Amazon 主图',
            variant_index: 0,
            thumbnail_url: '/api/v1/images/assets/suite/file',
            download_url: '/api/v1/images/assets/suite/file',
            created_at: '2026-11-14T01:00:00Z',
          },
        ],
      },
    ]

    const variants = flattenCampaignImageVariants(assets)
    expect(variants[0]).toMatchObject({
      suite_id: 'suite-1',
      platform: 'amazon-main',
    })
  })
})
