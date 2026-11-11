import { describe, expect, it } from 'vitest'

import {
  formatCoverage,
  operationStatusLabel,
  toMonitorSettingsPayload,
} from './operations'

describe('operations helpers', () => {
  it('格式化库存覆盖天数和补货状态', () => {
    expect(formatCoverage(2.56)).toBe('2.6 天')
    expect(formatCoverage(null)).toBe('数据不足')
    expect(operationStatusLabel('out_of_stock')).toBe('已缺货')
    expect(operationStatusLabel('reorder')).toBe('需要补货')
    expect(operationStatusLabel('healthy')).toBe('库存健康')
  })

  it('把百分比表单转换为后端费率', () => {
    const payload = toMonitorSettingsPayload({
      target_margin_rate: '30',
      low_stock_days: '8',
      lead_time_days: '21',
      safety_stock_days: '4',
      platform_fee_percent: '15',
      shipping_cost: '3.5',
      cost_increase_alert_rate: '8',
    })

    expect(payload.target_margin_rate).toBe(30)
    expect(payload.platform_fee_rate).toBe(0.15)
    expect(payload.lead_time_days).toBe(21)
  })
})
