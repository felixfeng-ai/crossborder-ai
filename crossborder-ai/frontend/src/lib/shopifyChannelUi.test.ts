import { describe, expect, it } from 'vitest'

import {
  pickInitialShopifyChannelId,
  resolveShopifyOrderView,
} from './shopifyChannelUi'


describe('shopify channel ui', () => {
  it('选择已有店铺时自动选中第一个渠道', () => {
    const channels = [{ id: 'store-a' }, { id: 'store-b' }]

    expect(pickInitialShopifyChannelId(channels, null)).toBe('store-a')
    expect(pickInitialShopifyChannelId(channels, 'store-b')).toBe('store-b')
  })

  it('接口失败时进入错误态，而不是显示暂无订单', () => {
    expect(
      resolveShopifyOrderView({
        selectedChannel: 'store-a',
        isLoading: false,
        isError: true,
        orderCount: 0,
      }),
    ).toBe('error')
  })

  it('仅成功返回空数组时显示空订单状态', () => {
    expect(
      resolveShopifyOrderView({
        selectedChannel: 'store-a',
        isLoading: false,
        isError: false,
        orderCount: 0,
      }),
    ).toBe('empty')
  })
})
