export interface OwnProductFormValues {
  title: string
  url?: string
  description?: string
  price?: string
  currency?: string
  brandName?: string
  moq?: string
  leadTimeDays?: string
  sku?: string
  stockQuantity?: string
  mainImageUrl?: string
}

function optionalNumber(value: string | undefined): number | undefined {
  const normalized = String(value || '').trim()
  if (!normalized) return undefined
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : undefined
}

/** 把表单字符串转换为自有商品 API 请求，空可选值不提交。 */
export function buildOwnProductPayload(form: OwnProductFormValues) {
  const payload: Record<string, unknown> = {
    title: form.title.trim(),
    origin_type: 'own',
    cost_currency: (form.currency || 'CNY').trim().toUpperCase() || 'CNY',
  }
  const optionalText = {
    url: form.url,
    description: form.description,
    brand_name: form.brandName,
    sku: form.sku,
    main_image_url: form.mainImageUrl,
  }
  for (const [key, value] of Object.entries(optionalText)) {
    const normalized = String(value || '').trim()
    if (normalized) payload[key] = normalized
  }
  const numeric = {
    price: optionalNumber(form.price),
    moq: optionalNumber(form.moq),
    lead_time_days: optionalNumber(form.leadTimeDays),
    stock_quantity: optionalNumber(form.stockQuantity),
  }
  for (const [key, value] of Object.entries(numeric)) {
    if (value !== undefined) payload[key] = value
  }
  return payload
}

export function productOriginLabel(originType: string | null | undefined): string {
  return originType === 'own' ? '自有货源' : '1688 货源'
}
