import type { ProductCandidate } from '@/types'

type UnknownRecord = Record<string, unknown>

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {}
}

function firstValue(data: UnknownRecord, ...keys: string[]): unknown {
  for (const key of keys) {
    const value = data[key]
    if (value !== null && value !== undefined && value !== '') return value
  }
  return null
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string') return null
  const normalized = value.trim().replace(/[¥$,%]/g, '')
  if (!normalized) return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

function toStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean)
  }
  if (typeof value !== 'string' || !value.trim()) return []
  return value
    .replace(/[，,；;]/g, '、')
    .split('、')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function normalizeSelectionProduct(value: unknown): ProductCandidate {
  const data = asRecord(value)
  const nameValue = firstValue(data, 'name', 'title', 'product_name', '商品名', '名称')

  return {
    name: typeof nameValue === 'string' ? nameValue.trim() : '',
    asin: typeof data.asin === 'string' ? data.asin.trim() || null : null,
    url: typeof data.url === 'string' ? data.url : null,
    image_url:
      typeof data.image_url === 'string' ? data.image_url.trim() || null : null,
    suggested_price_usd: toNumber(
      firstValue(
        data,
        'suggested_price_usd',
        'price_usd',
        'avg_price_usd',
        'price',
        '价格美元',
        '建议售价',
      ),
    ),
    cost_cny: toNumber(firstValue(data, 'cost_cny', '采购价', '成本', '成本人民币')),
    net_profit_usd: toNumber(
      firstValue(data, 'net_profit_usd', '单件净利', '净利'),
    ),
    net_margin: toNumber(firstValue(data, 'net_margin', '净利率', '利润率')),
    competition: toNumber(
      firstValue(data, 'competition', 'competition_level', '竞争度'),
    ),
    risk_tips: toStringList(
      firstValue(data, 'risk_tips', 'risks', '风险提示', '主要痛点'),
    ),
  }
}

export function isDisplayableSelectionProduct(
  product: ProductCandidate,
): boolean {
  return Boolean(product.name.trim())
}

export function normalizeSelectionProducts(value: unknown): ProductCandidate[] {
  if (!Array.isArray(value)) return []
  return value
    .map(normalizeSelectionProduct)
    .filter(isDisplayableSelectionProduct)
}
