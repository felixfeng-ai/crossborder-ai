import { describe, expect, it } from 'vitest'
import { getActionLabel } from './actionLabels'

describe('agent action labels', () => {
  it('为新业务工具提供明确的中文名称', () => {
    expect(getActionLabel('list_materials')).toBe('查询素材')
    expect(getActionLabel('generate_product_image')).toBe('生成商品图片')
    expect(getActionLabel('generate_product_video')).toBe('生成商品视频')
    expect(getActionLabel('create_marketing_video_plan')).toBe('生成营销视频方案')
    expect(getActionLabel('get_listing')).toBe('读取 Listing')
    expect(getActionLabel('edit_listing')).toBe('编辑 Listing')
    expect(getActionLabel('sync_shopify_operations')).toBe('同步 Shopify 运营数据')
    expect(getActionLabel('screen_ip_risk')).toBe('IP 风险初筛')
  })
})
