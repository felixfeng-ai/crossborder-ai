import { describe, expect, it } from 'vitest'
import { creditBreakdownLabel, formatCreditTotal } from './balance'


describe('billing credit balance presentation', () => {
  it('格式化真实钱包总额并解释来源', () => {
    expect(formatCreditTotal(99998)).toBe('99,998')
    expect(
      creditBreakdownLabel({
        plan_credits: 30,
        purchased_credits: 99968,
        total_credits: 99998,
      }),
    ).toBe('套餐额度 30 + 购买积分 99,968')
  })

  it('不把空值伪装成固定的 99998', () => {
    expect(formatCreditTotal(undefined)).toBe('0')
    expect(formatCreditTotal(null)).toBe('0')
  })
})
