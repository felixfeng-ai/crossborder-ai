import { describe, expect, it } from 'vitest'

import { buildCopyPrompt } from './prompt-builder'

describe('buildCopyPrompt', () => {
  it('拼入平台、语言、品牌调性和原始商品信息', () => {
    const prompt = buildCopyPrompt(
      '智能感应垃圾桶',
      {
        brand_name: 'CleanHome',
        tagline: '让家更简单',
        tone: 'professional',
        banned_words: ['全网最低价', '绝对安全'],
      },
      'amazon',
      'en',
    )

    expect(prompt).toContain('amazon')
    expect(prompt).toContain('en')
    expect(prompt).toContain('CleanHome')
    expect(prompt).toContain('让家更简单')
    expect(prompt).toContain('全网最低价')
    expect(prompt).toContain('绝对安全')
    expect(prompt).toContain('智能感应垃圾桶')
  })

  it('没有品牌配置时仍带平台违禁词规则', () => {
    const prompt = buildCopyPrompt('无线耳机', null)
    expect(prompt).toContain('平台违禁词硬性规则')
    expect(prompt).toContain('零风险')
    expect(prompt).toContain('无线耳机')
  })
})
