import { describe, expect, it } from 'vitest'

import {
  isDisplayableSelectionProduct,
  normalizeSelectionProduct,
} from './selectionReport'

describe('selection report product normalization', () => {
  it('normalizes title and price aliases from historical reports', () => {
    const product = normalizeSelectionProduct({
      asin: 'B000IMAGE1',
      title: '圣诞主题陶瓷马克杯礼盒',
      image_url: 'https://img.example.com/mug.jpg',
      price_usd: 32.99,
      rating: 4.6,
      features: '含杯垫和勺子',
    })

    expect(product.name).toBe('圣诞主题陶瓷马克杯礼盒')
    expect(product.asin).toBe('B000IMAGE1')
    expect(product.image_url).toBe('https://img.example.com/mug.jpg')
    expect(product.suggested_price_usd).toBe(32.99)
    expect(isDisplayableSelectionProduct(product)).toBe(true)
  })

  it('normalizes Chinese keys and percentage strings', () => {
    const product = normalizeSelectionProduct({
      商品名: '防碎圣诞树球套装',
      价格美元: '24.99',
      采购价: '¥45',
      净利率: '38%',
      竞争度: '4',
      主要痛点: '挂钩偏软、金色款易掉粉',
    })

    expect(product.name).toBe('防碎圣诞树球套装')
    expect(product.suggested_price_usd).toBe(24.99)
    expect(product.cost_cny).toBe(45)
    expect(product.net_margin).toBe(38)
    expect(product.competition).toBe(4)
    expect(product.risk_tips).toEqual(['挂钩偏软', '金色款易掉粉'])
  })

  it('filters items without a product name', () => {
    const product = normalizeSelectionProduct({ price_usd: 19.99 })
    expect(isDisplayableSelectionProduct(product)).toBe(false)
  })
})
