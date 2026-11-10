// ============================================================================
// VeyaShip - Agent 结构化报告类型
// 与后端 data.structured 的 JSON 契约对齐（snake_case 零转换直喂）
// ============================================================================

/** 市场指标 —— 对应后端 data.structured.market */
export interface MarketMetrics {
  monthly_search_volume: number | null // 月搜索量
  active_listings: number | null // 在售 Listing 数
  avg_price_usd: number | null // 平均售价（美元）
  head_concentration: number | null // 头部集中度（0-100 百分数）
  competition_level: number | null // 竞争度（1-5）
  price_war_level: number | null // 价格战程度（1-5）
  new_product_survival_rate: number | null // 新品存活率（0-100 百分数）
  user_pains?: string[] // 用户痛点
}

/** 候选商品 —— 对应 data.structured.products[] */
export interface ProductCandidate {
  name: string
  url?: string | null // Amazon 搜索结果链接
  suggested_price_usd: number | null // 建议售价（美元）
  cost_cny?: number | null // 1688 采购成本（人民币）
  net_profit_usd: number | null // 单件净利（美元）
  net_margin: number | null // 净利率（0-100 百分数）
  competition: number | null // 竞争度星级（1-5）
  risk_tips: string[] // 风险提示
}

/** 推荐结论 —— 对应 data.structured.recommendation */
export interface SelectionRecommendation {
  top_pick: string // 首选商品/方向
  url?: string | null // 首选商品/方向对应的搜索链接
  verdict: string // 一句话结论
  score?: number | null // 综合评分（0-10）
  reasons: string[] // 推荐理由
  risks: string[] // 风险
  entry_advice?: string // 切入建议
}

/** 统一报告结构 —— select_products 与 analyze_category 共用 */
export interface SelectionReport {
  keyword?: string
  market?: Partial<MarketMetrics>
  products?: ProductCandidate[]
  recommendation?: SelectionRecommendation
}

/** Agent 执行步骤 —— 对应 /agent/run 返回的 steps[] */
export interface AgentStep {
  action: string
  status: 'success' | 'failed' | 'partial'
  summary?: string
  error?: string
  data?: {
    keyword?: string
    report?: string
    structured?: SelectionReport | null
  }
}
