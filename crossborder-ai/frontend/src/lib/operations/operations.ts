export interface MonitorSettingsForm {
  target_margin_rate: string
  low_stock_days: string
  lead_time_days: string
  safety_stock_days: string
  platform_fee_percent: string
  shipping_cost: string
  cost_increase_alert_rate: string
}

export interface MonitorSettings {
  target_margin_rate: number
  low_stock_days: number
  lead_time_days: number
  safety_stock_days: number
  platform_fee_rate: number
  shipping_cost: number
  cost_increase_alert_rate: number
}

export interface ReplenishmentItem {
  variant_id: string
  product_id: string
  product_title: string | null
  sku: string
  selling_price: number | null
  cost_price: number | null
  stock_quantity: number
  daily_sales_rate: number
  margin_rate: number | null
  net_profit: number | null
  days_cover: number | null
  reorder_point: number | null
  suggested_quantity: number
  status: 'out_of_stock' | 'reorder' | 'healthy' | 'insufficient_data'
}

export function formatCoverage(days: number | null): string {
  return days == null ? '数据不足' : `${days.toFixed(1)} 天`
}

export function operationStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    out_of_stock: '已缺货',
    reorder: '需要补货',
    healthy: '库存健康',
    insufficient_data: '数据不足',
  }
  return labels[status] || status
}

export function toMonitorSettingsPayload(form: MonitorSettingsForm) {
  const number = (value: string, fallback = 0) => {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : fallback
  }
  return {
    target_margin_rate: number(form.target_margin_rate),
    low_stock_days: Math.trunc(number(form.low_stock_days)),
    lead_time_days: Math.trunc(number(form.lead_time_days)),
    safety_stock_days: Math.trunc(number(form.safety_stock_days)),
    platform_fee_rate: number(form.platform_fee_percent) / 100,
    shipping_cost: number(form.shipping_cost),
    cost_increase_alert_rate: number(form.cost_increase_alert_rate),
  }
}
