// ============================================================================
// VeyaShip - TypeScript Type Definitions
// ============================================================================

// --- User & Auth ---
export interface User {
  id: number
  email: string
  username: string
  full_name: string | null
  avatar_url: string | null
  company_name: string | null
  website: string | null
  description: string | null
  is_active: boolean
  is_verified: boolean
  plan: UserPlan
  credits: number
  shopify_shop_name: string | null
  created_at: string
  updated_at: string
  is_admin?: boolean
}

export type UserPlan = 'free' | 'standard' | 'starter' | 'professional' | 'enterprise'

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  username: string
  password: string
  full_name?: string
  company_name?: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
}

// --- Product ---
export interface Product {
  id: number
  owner_id: number
  title: string
  description: string | null
  sku: string | null
  barcode: string | null
  price: number
  compare_at_price: number | null
  cost_price: number | null
  stock_quantity: number
  is_active: boolean
  image_url: string | null
  additional_images: string | null
  category: string | null
  tags: string | null
  shopify_product_id: string | null
  weight: number | null
  weight_unit: string
  created_at: string
  updated_at: string
}

export interface ProductCreate {
  title: string
  description?: string
  sku?: string
  price: number
  compare_at_price?: number
  cost_price?: number
  stock_quantity?: number
  image_url?: string
  category?: string
  tags?: string[]
  weight?: number
  weight_unit?: string
}

export interface ProductListResponse {
  items: Product[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// --- Listing ---
export interface Listing {
  id: number
  owner_id: number
  product_id: number | null
  platform: ListingPlatform
  platform_listing_id: string | null
  status: ListingStatus
  title: string
  description: string | null
  bullet_points: string | null
  search_terms: string | null
  seo_title: string | null
  seo_description: string | null
  price: number
  sale_price: number | null
  currency: string
  main_image_url: string | null
  additional_image_urls: string | null
  ai_generated: boolean
  ai_model_used: string | null
  created_at: string
  updated_at: string
  published_at: string | null
  variants: ListingVariant[]
}

export interface ListingVariant {
  id: number
  listing_id: number
  option1_name: string | null
  option1_value: string | null
  option2_name: string | null
  option2_value: string | null
  price: number
  stock_quantity: number
  image_url: string | null
  is_active: boolean
}

export type ListingPlatform =
  | 'shopify'
  | 'amazon'
  | 'ebay'
  | 'etsy'
  | 'walmart'
  | 'aliexpress'
  | 'shopee'
  | 'lazada'
  | 'manual'

export type ListingStatus =
  | 'draft'
  | 'ai_generated'
  | 'reviewed'
  | 'published'
  | 'failed'

// --- Content Generation ---
export interface ContentGenerateRequest {
  listing_id?: number
  product_id?: number
  source_text?: string
  source_image_url?: string
  title?: string
  content_type: ContentType
  platform: string
  target_language?: string
  template_id?: number
  tone?: string
  target_audience?: string
  keywords?: string[]
  max_length?: number
  generate_image?: boolean
  image_prompt?: string
}

export interface ContentGenerateResponse {
  id: number
  content_type: string
  status: string
  generated_text: string | null
  generated_image_url: string | null
  model_used: string
  tokens_used: number | null
  credits_cost: number | null
  suggestions: Record<string, unknown>[] | null
  seo_score: number | null
  created_at: string
}

export type ContentType =
  | 'product_title'
  | 'product_description'
  | 'bullet_points'
  | 'seo_title'
  | 'seo_description'
  | 'social_media_post'
  | 'ad_copy'
  | 'email_marketing'
  | 'blog_post'
  | 'image_prompt'
  | 'translation'
  | 'optimization'

export interface ContentTemplate {
  id: number
  name: string
  description: string | null
  content_type: string
  platform: string | null
  language: string
  tone: string | null
  target_audience: string | null
  is_system: boolean
  is_active: boolean
  usage_count: number
  avg_rating: number | null
}

// --- Payment & Subscription ---
export interface PlanInfo {
  name: string
  display_name: string
  description: string
  monthly_price: number
  yearly_price: number
  credits_per_month: number
  features: string[]
}

export interface Subscription {
  id: number
  user_id: number
  plan_name: string
  status: string
  billing_interval: string
  amount: number
  currency: string
  current_period_start: string | null
  current_period_end: string | null
  trial_end: string | null
  canceled_at: string | null
  credits_per_period: number
  credits_used: number
  features: Record<string, unknown> | null
  is_active: boolean
  created_at: string
}

export interface Invoice {
  id: number
  subscription_id: number | null
  amount: number
  currency: string
  status: string
  payment_method: string | null
  billing_reason: string | null
  receipt_url: string | null
  invoice_pdf_url: string | null
  created_at: string
  paid_at: string | null
}

// --- Analytics ---
export interface DashboardData {
  products: { total: number }
  listings: { draft: number; published: number; total: number }
  content: {
    total_generations: number
    recent_7_days: number
    credits_remaining: number
    credits_used: number
  }
  platforms: Record<string, number>
}

export interface UsageTrend {
  days: number
  trend: { date: string; count: number }[]
  total: number
}

// --- API Error ---
export interface ApiError {
  detail: string
  status_code?: number
}

// --- Pagination ---
export interface PaginationParams {
  page?: number
  page_size?: number
}

// --- Agent 结构化报告 ---
export * from './agent'
