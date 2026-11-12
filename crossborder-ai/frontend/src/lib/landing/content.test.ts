import { describe, expect, it } from 'vitest'
import {
  FALLBACK_CREDIT_PACKS,
  FALLBACK_PLANS,
  LANDING_FEATURES,
  SUPPORTED_COPY_PLATFORMS,
  planDisplayName,
  planValidityLabel,
} from './content'


describe('landing content facts', () => {
  it('展示当前 11 个文案平台与真实发布边界', () => {
    expect(SUPPORTED_COPY_PLATFORMS).toHaveLength(11)
    expect(SUPPORTED_COPY_PLATFORMS).toEqual(
      expect.arrayContaining(['SHEIN', 'Shopee', 'Lazada']),
    )
  })

  it('功能内容覆盖 VOC、素材、字幕配音和店铺连接', () => {
    const text = LANDING_FEATURES.map((item) => `${item.title} ${item.desc}`).join(' ')
    expect(text).toContain('VOC')
    expect(text).toContain('字幕')
    expect(text).toContain('配音')
    expect(text).toContain('素材中心')
    expect(text).toContain('Amazon')
  })

  it('套餐回退值与线上接口一致', () => {
    expect(FALLBACK_PLANS.map((plan) => plan.price)).toEqual([0, 99, 249])
    expect(FALLBACK_PLANS.map((plan) => plan.monthly_credits)).toEqual([30, 800, 2000])
    expect(FALLBACK_CREDIT_PACKS.map((pack) => pack.credits)).toEqual([50, 200, 500, 1200])
    expect(planDisplayName('free')).toBe('免费版')
    expect(planValidityLabel(FALLBACK_PLANS[1])).toBe('30 天有效')
  })
})
