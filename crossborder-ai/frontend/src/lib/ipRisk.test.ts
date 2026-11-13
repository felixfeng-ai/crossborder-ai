import { describe, expect, it } from 'vitest'

import {
  coverageLabel,
  ipRiskLabel,
  ipSeverityLabel,
  isIpPublishBlocked,
} from './ipRisk'

describe('IP risk display helpers', () => {
  it('maps risk and coverage states to clear Chinese labels', () => {
    expect(ipRiskLabel('high')).toBe('高风险')
    expect(ipRiskLabel('unknown')).toBe('风险未知')
    expect(coverageLabel('checked')).toBe('已检查')
    expect(coverageLabel('not_checked')).toBe('未检查')
    expect(ipSeverityLabel('info')).toBe('提示')
  })

  it('only blocks publishing for high risk', () => {
    expect(isIpPublishBlocked('high')).toBe(true)
    expect(isIpPublishBlocked('medium')).toBe(false)
    expect(isIpPublishBlocked('unknown')).toBe(false)
  })
})
