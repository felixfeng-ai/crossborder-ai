import { describe, expect, it } from 'vitest'

import {
  normalizeShopifyDomain,
  storePlatformLabel,
  storeStatusLabel,
  supportedStoreProviders,
} from './stores'

describe('commerce store helpers', () => {
  it('统一展示 Shopify、Amazon 和 Temu 店铺', () => {
    expect(supportedStoreProviders().map((provider) => provider.id)).toEqual([
      'shopify',
      'amazon',
      'temu',
    ])
    expect(storePlatformLabel('amazon')).toBe('Amazon')
    expect(storePlatformLabel('temu')).toBe('Temu')
    expect(storeStatusLabel('active')).toBe('已连接')
    expect(storeStatusLabel('expired')).toBe('授权异常')
  })

  it('把 Shopify 输入规范成域名', () => {
    expect(normalizeShopifyDomain(' demo-store ')).toBe('demo-store')
    expect(
      normalizeShopifyDomain('https://demo-store.myshopify.com/admin'),
    ).toBe('demo-store')
    expect(
      normalizeShopifyDomain('https://demo-store.myshopify.com'),
    ).toBe('demo-store')
    expect(normalizeShopifyDomain('')).toBe('')
  })
})
