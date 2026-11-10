import { describe, expect, it } from 'vitest'

import { buildBulkVariantPatch, parseAttributeGroups } from './catalog'

describe('catalog helpers', () => {
  it('解析变体矩阵文本并去除空值和重复值', () => {
    const groups = parseAttributeGroups(
      '颜色=黑色, 白色,黑色\n尺寸= M , L,\n\n材质 = 304 不锈钢 ',
    )

    expect(groups).toEqual({
      颜色: ['黑色', '白色'],
      尺寸: ['M', 'L'],
      材质: ['304 不锈钢'],
    })
  })

  it('批量修改只提交用户实际填写的字段', () => {
    const payload = buildBulkVariantPatch(['v1', 'v2'], {
      price: '39.9',
      cost_price: '',
      stock_quantity: '12',
      is_active: 'false',
      image_url: '',
    })

    expect(payload).toEqual({
      variant_ids: ['v1', 'v2'],
      price: 39.9,
      stock_quantity: 12,
      is_active: false,
    })
  })
})
