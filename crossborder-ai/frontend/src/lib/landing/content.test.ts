import { describe, expect, it } from 'vitest'
import {
  FALLBACK_CREDIT_PACKS,
  FALLBACK_PLANS,
  LANDING_FEATURES,
  LANDING_STATS,
  LANDING_VIDEO_MODES,
  LANDING_VIDEO_STYLES,
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
    expect(text).toContain('全局')
    expect(text).toContain('页面上下文')
    expect(text).toContain('IP')
    expect(text).toContain('政策')
  })

  it('首页使用当前真实工具数量', () => {
    expect(LANDING_STATS).toContainEqual({
      value: '24',
      label: 'AI 业务工具',
      tone: 'text-slate-100',
    })
  })

  it('首页视频能力覆盖三种真实工作流和结构化风格', () => {
    expect(LANDING_VIDEO_MODES.map((item) => item.id)).toEqual([
      'marketing',
      'storyboard',
      'single',
    ])
    expect(LANDING_VIDEO_MODES.every((item) => item.title && item.desc)).toBe(true)
    expect(LANDING_VIDEO_STYLES).toEqual(
      expect.arrayContaining(['高端静奢', '真实生活', '电影叙事', '节日氛围']),
    )
  })

  it('套餐回退值与线上接口一致', () => {
    expect(FALLBACK_PLANS.map((plan) => plan.price)).toEqual([0, 99, 249])
    expect(FALLBACK_PLANS.map((plan) => plan.monthly_credits)).toEqual([30, 800, 3000])
    expect(FALLBACK_CREDIT_PACKS.map((pack) => pack.credits)).toEqual([50, 200, 500, 1200])
    expect(planDisplayName('free')).toBe('免费版')
    expect(planValidityLabel(FALLBACK_PLANS[1])).toBe('30 天有效')
  })
})
