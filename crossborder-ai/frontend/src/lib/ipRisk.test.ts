import { describe, expect, it } from 'vitest'

import {
  coverageLabel,
  evidenceExpiryState,
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

  it('blocks high risk and incomplete required checks', () => {
    const report = (
      status: string,
      overall_risk: string,
      text: string,
      image: string,
    ) => ({
      report_id: 'report',
      status,
      overall_risk,
      coverage: { text, image },
      summary: {},
      risks: [],
      ruleset_version: 'test',
    })

    expect(isIpPublishBlocked(null)).toBe(true)
    expect(
      isIpPublishBlocked(report('completed', 'high', 'checked', 'checked')),
    ).toBe(true)
    expect(
      isIpPublishBlocked(
        report('partial', 'unknown', 'checked', 'not_checked'),
      ),
    ).toBe(true)
    expect(
      isIpPublishBlocked(report('failed', 'low', 'checked', 'failed')),
    ).toBe(true)
    expect(
      isIpPublishBlocked(
        report('completed', 'low', 'not_checked', 'checked'),
      ),
    ).toBe(true)
    expect(
      isIpPublishBlocked(
        report('completed', 'low', 'checked', 'not_checked'),
      ),
    ).toBe(false)
    expect(
      isIpPublishBlocked(
        report('completed', 'medium', 'checked', 'checked'),
      ),
    ).toBe(false)
  })

  it('labels evidence expiry states for UI reminders', () => {
    const now = new Date('2026-11-13T00:00:00Z')

    expect(evidenceExpiryState(null, now)).toEqual({
      status: 'permanent',
      label: '长期有效',
    })
    expect(
      evidenceExpiryState('2026-11-12T23:59:59Z', now),
    ).toEqual({ status: 'expired', label: '已过期' })
    expect(
      evidenceExpiryState('2026-12-01T00:00:00Z', now),
    ).toEqual({ status: 'expiring', label: '18 天后到期' })
    expect(
      evidenceExpiryState('2027-01-15T00:00:00Z', now),
    ).toEqual({ status: 'valid', label: '有效期至 2027-01-15' })
  })
})
