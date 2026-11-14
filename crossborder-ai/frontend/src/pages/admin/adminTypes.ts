export type MetricSummary = {
  samples: number
  p75: number | null
  ratings: Record<'good' | 'needs-improvement' | 'poor', number>
}

export type AdminOverview = {
  range_days: number
  business: {
    total_users: number
    paid_users: number
    plan_distribution: Record<string, number>
    pending_upgrades: number
    pending_credit_purchases: number
    feedback_open: number
    revenue: number
  }
  traffic: {
    pv: number
    uv: number
    sessions: number
    daily: { date: string; pv: number; uv: number }[]
    top_paths: { path: string; pv: number; uv: number }[]
    devices: { device: string; pv: number }[]
    countries: { country: string; pv: number }[]
  }
  performance: {
    metrics: Record<string, MetricSummary>
    groups?: Record<
      'all' | 'china' | 'overseas' | 'mobile',
      { metrics: Record<string, MetricSummary> }
    >
  }
}

export type FeedbackTicket = {
  id: string
  type: string
  title: string
  content: string
  page_path: string
  page_title: string
  browser_info: Record<string, unknown>
  status: 'open' | 'in_progress' | 'resolved' | 'closed'
  priority: 'low' | 'normal' | 'high' | 'urgent'
  assigned_to: string | null
  note: string
  created_at: string
  updated_at: string
  resolved_at: string | null
}

export type PlanVersion = {
  id: string
  plan_key: string
  version: number
  name: string
  description: string
  rank: number
  price_cents: number
  first_month_price_cents: number
  annual_price_cents: number
  annual_full_price_cents: number
  monthly_credits: number
  first_month_bonus_credits: number
  valid_days: number
  features: string[]
  status: 'draft' | 'published' | 'archived'
  effective_at: string | null
  created_at: string
}

export type PublicPlan = {
  id: string
  name: string
  price: number
  first_month_price: number
  annual_price: number
  annual_full_price: number
  monthly_credits: number
  first_month_bonus_credits: number
  features: string[]
  validity_days: number
  recommended: boolean
  rank: number
}
