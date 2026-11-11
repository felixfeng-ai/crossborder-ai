export type LandingFeatureIcon =
  | 'agent'
  | 'market'
  | 'compliance'
  | 'media'
  | 'channel'
  | 'ops'

export interface LandingFeature {
  icon: LandingFeatureIcon
  title: string
  desc: string
}

export interface LandingPlan {
  id: string
  name: string
  price: number
  price_label?: string
  monthly_credits?: number
  description: string
  features: string[]
  validity_days: number
  recommended: boolean
}

export interface LandingCreditPack {
  id: string
  name: string
  credits: number
  price: number
}

export const SUPPORTED_COPY_PLATFORMS = [
  'Amazon',
  'Shopify',
  'eBay',
  'Etsy',
  'SHEIN',
  'Temu',
  'TikTok Shop',
  'AliExpress',
  'Walmart',
  'Shopee',
  'Lazada',
]

export const LANDING_FEATURES: LandingFeature[] = [
  {
    icon: 'agent',
    title: 'AI Agent 与自动化执行',
    desc: '20 个业务工具、6 个预设工作流；长任务异步执行，并实时展示步骤、结果和失败原因。',
  },
  {
    icon: 'market',
    title: '市场判断与 VOC 评论洞察',
    desc: '分析品类、竞争和利润机会；导入评论提炼痛点、卖点与成交异议，并反哺 Listing 生成。',
  },
  {
    icon: 'compliance',
    title: 'Listing、合规与版本闭环',
    desc: '生成标题、描述、卖点和 SEO；合规结果绑定当前版本，内容修改后旧报告自动失效。',
  },
  {
    icon: 'media',
    title: '商品图、视频与营销成片',
    desc: '上传素材、处理白底图与平台尺寸；商品图生视频、营销分镜、SRT 字幕和 AI 配音统一沉淀到素材中心。',
  },
  {
    icon: 'channel',
    title: 'SKU 与渠道连接',
    desc: '配置售价、成本、库存和变体；11 个平台生成 Listing 文案，Shopify 支持草稿发布，Amazon 支持 SP-API 授权连接。',
  },
  {
    icon: 'ops',
    title: '运营监控与整店巡检',
    desc: '按 SKU 检查毛利、库存覆盖、补货点、渠道异常和商品信息缺口；Standard 起支持自动巡检。',
  },
]

export const LANDING_PIPELINE = [
  { step: '01', icon: 'source', title: '来源商品', detail: '链接、CSV 或手动录入' },
  { step: '02', icon: 'market', title: '市场与利润', detail: '竞争、成本与风险' },
  { step: '03', icon: 'voice', title: 'VOC 与 Listing', detail: '评论洞察、文案与合规' },
  { step: '04', icon: 'media', title: '图片与视频', detail: '素材、字幕与营销成片' },
  { step: '05', icon: 'channel', title: '发布与巡检', detail: '渠道连接、SKU 与待办' },
] as const

export const LANDING_FLOW = [
  { step: '01', title: '市场判断', desc: '分析机会、竞争和利润' },
  { step: '02', title: '利润与风险', desc: '形成是否进入的决策' },
  { step: '03', title: 'VOC + Listing', desc: '真实反馈反哺内容生成' },
  { step: '04', title: '图片与视频', desc: '主图、成片、字幕与配音' },
  { step: '05', title: '发布与巡检', desc: 'SKU 配置、店铺发布和监控' },
]

export const LANDING_AGENT_EXAMPLES = [
  {
    prompt: '"分析这批耳机评论，用户最在意什么？"',
    steps: '导入评论 → 提炼痛点和卖点 → 识别成交异议 → 把 VOC 结论带入 Listing',
  },
  {
    prompt: '"把这款 1688 商品做成 Amazon Listing"',
    steps: '抓取商品 → 结合市场与 VOC → 生成标题、描述和卖点 → 合规检查',
  },
  {
    prompt: '"基于商品图做一条 15 秒营销短视频"',
    steps: '生成创意和分镜 → 预估积分 → 视频工作台成片 → SRT 字幕与 AI 配音',
  },
]

export const FALLBACK_CREDIT_PACKS: LandingCreditPack[] = [
  { id: 'pack_200', name: '入门积分包', credits: 200, price: 19 },
  { id: 'pack_500', name: '常用积分包', credits: 500, price: 45 },
  { id: 'pack_1200', name: '专业积分包', credits: 1200, price: 99 },
]

export const FALLBACK_PLANS: LandingPlan[] = [
  {
    id: 'free',
    name: 'Free',
    price: 0,
    price_label: '免费',
    monthly_credits: 30,
    description: '试试基本功能',
    validity_days: 0,
    recommended: false,
    features: [
      '每月 30 AI 积分',
      '1688 商品抓取与利润测算',
      'Listing、合规与 VOC 评论洞察',
      '品类分析与 AI Insights 各 10 次/月',
    ],
  },
  {
    id: 'standard',
    name: 'Standard',
    price: 99,
    price_label: '¥99/月',
    monthly_credits: 800,
    description: '适合个人卖家',
    validity_days: 30,
    recommended: true,
    features: [
      '每月 800 AI 积分',
      'AI Agent、批量处理与自动巡检',
      'Shopify 草稿发布与运营同步',
      '11 个平台 Listing 文案生成',
      '每月 10 次手动整店巡检',
    ],
  },
  {
    id: 'professional',
    name: 'Professional',
    price: 249,
    price_label: '¥249/月',
    monthly_credits: 2000,
    description: '适合工作室与专业卖家',
    validity_days: 30,
    recommended: false,
    features: [
      '每月 2,000 AI 积分',
      '所有 Standard 功能',
      'AI 图片、商品视频与营销成片',
      '字幕、AI 配音与素材中心',
      '每月 20 次手动整店巡检',
      '优先技术支持',
    ],
  },
]

export function planDisplayName(planId: string): string {
  return planId === 'free' ? '免费版' : planId
}

export function planValidityLabel(plan: LandingPlan): string {
  return plan.validity_days > 0 ? `${plan.validity_days} 天有效` : '长期有效'
}

export function planPriceLabel(plan: LandingPlan): string {
  if (plan.price === 0) return '¥0'
  return `¥${plan.price.toLocaleString('zh-CN')}`
}
