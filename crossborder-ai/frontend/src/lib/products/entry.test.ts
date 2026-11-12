import { describe, expect, it } from 'vitest'
import {
  buildOwnProductPayload,
  productOriginLabel,
} from './entry'

describe('own supply product entry', () => {
  it('normalizes numeric fields and omits empty optional values', () => {
    const payload = buildOwnProductPayload({
      title: '  自有品牌保温杯  ',
      url: '',
      description: ' 500ml ',
      price: '23.5',
      currency: 'cny',
      brandName: 'VeyaHome',
      moq: '50',
      leadTimeDays: '7',
      sku: 'OWN-500',
      stockQuantity: '120',
      mainImageUrl: '/api/v1/images/assets/demo/file',
    })

    expect(payload).toMatchObject({
      title: '自有品牌保温杯',
      description: '500ml',
      price: 23.5,
      cost_currency: 'CNY',
      moq: 50,
      lead_time_days: 7,
      stock_quantity: 120,
      origin_type: 'own',
    })
    expect(payload.url).toBeUndefined()
  })

  it('labels product origin and cost semantics', () => {
    expect(productOriginLabel('own')).toBe('自有货源')
    expect(productOriginLabel('1688')).toBe('1688 货源')
  })
})
