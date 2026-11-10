export interface CatalogVariant {
  id: string
  product_id: string
  product_title: string
  sku: string
  name: string | null
  attributes: Record<string, string>
  price: number | null
  cost_price: number | null
  stock_quantity: number
  barcode: string | null
  image_url: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface PlatformReadinessCheck {
  id: string
  status: 'pass' | 'warning' | 'error'
  message: string
}

export interface CatalogListing {
  id: string
  product_id: string
  product_title: string
  platform: string
  language: string
  title: string
  status: string
  compliance_status: string
  version: number
  bullet_count: number
  readiness: {
    platform: string
    label: string
    ok: boolean
    score: number
    checks: PlatformReadinessCheck[]
  }
  created_at: string
  updated_at: string
}

export interface BulkEditableFields {
  price: string
  cost_price: string
  stock_quantity: string
  is_active: '' | 'true' | 'false'
  image_url: string
}

export function parseAttributeGroups(value: string): Record<string, string[]> {
  const groups: Record<string, string[]> = {}
  for (const line of value.split(/\r?\n/)) {
    const separator = line.search(/[=:：]/)
    if (separator < 0) continue
    const key = line.slice(0, separator).trim()
    const values = line
      .slice(separator + 1)
      .split(/[,，]/)
      .map((item) => item.trim())
      .filter(Boolean)
    if (!key || values.length === 0) continue
    groups[key] = [...new Set(values)]
  }
  return groups
}

export function buildBulkVariantPatch(
  variantIds: string[],
  fields: BulkEditableFields,
): Record<string, unknown> {
  const payload: Record<string, unknown> = { variant_ids: variantIds }

  const price = Number(fields.price)
  if (fields.price.trim() && Number.isFinite(price)) payload.price = price

  const costPrice = Number(fields.cost_price)
  if (fields.cost_price.trim() && Number.isFinite(costPrice)) payload.cost_price = costPrice

  const stock = Number(fields.stock_quantity)
  if (fields.stock_quantity.trim() && Number.isInteger(stock) && stock >= 0) {
    payload.stock_quantity = stock
  }

  if (fields.is_active === 'true') payload.is_active = true
  if (fields.is_active === 'false') payload.is_active = false

  if (fields.image_url.trim()) payload.image_url = fields.image_url.trim()
  return payload
}
