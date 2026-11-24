import type { ProductCandidate, SourceSupplierItem } from '@/types'

type SourcingProduct = Pick<
  ProductCandidate,
  'name' | 'asin' | 'image_url'
>

type SelectedSource = Pick<
  SourceSupplierItem,
  'title' | 'url' | 'price' | 'moq'
>

/** 从 Amazon 候选商品生成明确的 1688 找货指令。 */
export function buildFindSourcesPrompt(product: SourcingProduct): string {
  const lines = [
    '请为下面 Amazon 候选商品在 1688 找相似货源。',
    `商品：${product.name}`,
  ]
  if (product.asin) lines.push(`Amazon ASIN：${product.asin}`)
  if (product.image_url) {
    lines.push(`商品主图：${product.image_url}`)
  }
  lines.push(
    '请先把标题和规格提炼成简洁中文采购关键词，并调用 find_1688_sources。',
    product.image_url
      ? '有商品主图时优先使用图片搜索，图片失败再改用关键词。'
      : '当前没有可用主图，请使用关键词搜索。',
    '结果只能称为相似货源，不要宣称同款；不要自动询价、加购、下单或付款。',
  )
  return lines.join('\n')
}

/** 用户选定货源后，只进入真实利润分析，不执行采购动作。 */
export function buildProfitFromSourcePrompt(source: SelectedSource): string {
  const lines = [
    '请使用 analyze_product_decision 分析下面这个 1688 货源能不能做。',
    `商品：${source.title}`,
    `1688 链接：${source.url}`,
  ]
  if (source.price) lines.push(`页面采购价：${source.price}`)
  if (source.moq != null) lines.push(`MOQ：${source.moq}`)
  lines.push(
    '采购价、物流、平台佣金或履约费用缺少时请明确向我补充。',
    '只做利润和风险分析，不要自动下单或付款；也不要自动询价、加购。',
  )
  return lines.join('\n')
}
