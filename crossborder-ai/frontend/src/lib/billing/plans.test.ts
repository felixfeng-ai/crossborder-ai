import { describe, expect, it } from 'vitest'
import { planAccessState } from './plans'


describe('billing plan access', () => {
  it('只允许升级到更高套餐', () => {
    expect(planAccessState('free', 'standard')).toBe('available')
    expect(planAccessState('standard', 'professional')).toBe('available')
    expect(planAccessState('standard', 'free')).toBe('included')
    expect(planAccessState('professional', 'standard')).toBe('included')
  })

  it('当前套餐不可重复申请', () => {
    expect(planAccessState('free', 'free')).toBe('current')
    expect(planAccessState('standard', 'standard')).toBe('current')
    expect(planAccessState('professional', 'professional')).toBe('current')
  })
})
