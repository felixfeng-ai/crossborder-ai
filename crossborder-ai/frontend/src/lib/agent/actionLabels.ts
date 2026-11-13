const ACTION_LABELS: Record<string, string> = {
  scrape_1688: '抓取商品',
  analyze_product_decision: '商品决策分析',
  create_product: '保存商品',
  generate_listing: '生成 Listing',
  compliance_check: '合规审查',
  compliance_fix: '合规修正',
  screen_ip_risk: 'IP 风险初筛',
  search_platform_policies: '检索平台政策',
  calculate_profit: '利润测算',
  select_products: 'AI 选品',
  analyze_category: '品类市场分析',
  store_check: '店铺巡检',
  monitor_products: '运营监控',
  self_reflect: '内容质量检查',
  push_to_shopify: '发布到 Shopify',
  list_materials: '查询素材',
  generate_product_image: '生成商品图片',
  generate_product_video: '生成商品视频',
  create_marketing_video_plan: '生成营销视频方案',
  get_listing: '读取 Listing',
  edit_listing: '编辑 Listing',
  sync_shopify_operations: '同步 Shopify 运营数据',
  answer: '回复',
}

/** 对外只展示中文业务动作，避免把内部工具名直接暴露给卖家。 */
export function getActionLabel(action: string): string {
  return ACTION_LABELS[action] || '执行任务'
}
