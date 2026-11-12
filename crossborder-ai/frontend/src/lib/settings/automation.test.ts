import { describe, expect, it } from 'vitest'

import {
  automationStatusLabel,
  effectiveAutomationEnabled,
} from './automation'

describe('automation settings helpers', () => {
  it('展示真实任务状态', () => {
    expect(automationStatusLabel('never')).toBe('未运行')
    expect(automationStatusLabel('success')).toBe('成功')
    expect(automationStatusLabel('failed')).toBe('失败')
  })

  it('Free 套餐即使保留配置也不实际启用', () => {
    expect(effectiveAutomationEnabled('free', true)).toBe(false)
    expect(effectiveAutomationEnabled('standard', true)).toBe(true)
    expect(effectiveAutomationEnabled('professional', false)).toBe(false)
  })
})
