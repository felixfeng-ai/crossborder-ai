export type LandingFeatureIcon =
  | 'agent'
  | 'assistant'
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
  trial_once?: boolean
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
    icon: 'assistant',
    title: '全局 AI 决策助手与自动化执行',
    desc: '在图片台、视频台和经营页面随时打开 AI 侧栏，自动带入当前页面上下文；长任务异步执行，并实时展示步骤、结果和失败原因。',
  },
  {
    icon: 'market',
    title: '市场判断与 VOC 评论洞察',
    desc: '分析品类、竞争和利润机会；导入评论提炼痛点、卖点与成交异议，并反哺 Listing 生成。',
  },
  {
    icon: 'compliance',
    title: 'Listing、IP 风险与政策知识库',
    desc: '生成标题、描述、卖点和 SEO；合规检查覆盖违禁词、品牌与认证声称，并提供 IP 风险初筛和官方平台政策依据。',
  },
  {
    icon: 'media',
    title: '商品图、视频与营销成片',
    desc: '上传素材、处理白底图与平台尺寸；商品图生视频、营销分镜、SRT 字幕和 AI 配音统一沉淀到素材中心。',
  },
  {
    icon: 'channel',
    title: 'SKU 与渠道连接',
    desc: '配置售价、成本、库存和变体；11 个平台生成 Listing 文案，Shopify 支持草稿发布，Amazon 支持 SP-API Listing 发布。',
  },
  {
    icon: 'ops',
    title: '运营监控与整店巡检',
    desc: '按 SKU 检查毛利、库存覆盖、补货点、渠道异常和商品信息缺口；Standard 起支持自动巡检和任务开关。',
  },
]

export const LANDING_ASSISTANT_CONTEXT = [
  {
    page: '图片工作台',
    detail: '当前素材 · 平台预设',
    result: '检查主图、建议白底处理、继续生成商品视频',
  },
  {
    page: '视频工作台',
    detail: '视频模式 · 当前首帧',
    result: '优化镜头提示、检查首帧、估算积分',
  },
  {
    page: 'Listing 中心',
    detail: '商品 · 内容版本',
    result: '生成内容、执行合规与 IP 风险初筛、查询政策依据',
  },
] as const

export const LANDING_STATS = [
  { value: '24', label: 'AI 业务工具', tone: 'text-slate-100' },
  { value: '6', label: '预设工作流', tone: 'text-amber-400' },
  { value: '11', label: '平台文案支持', tone: 'text-emerald-400' },
  { value: '2', label: '真实店铺连接', tone: 'text-amber-400' },
] as const

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
    prompt: '"这张商品主图适合 TikTok Shop 吗？"',
    steps: '读取当前素材与平台预设 → 检查构图和主图要求 → 给出修改建议 → 继续生成视频',
  },
  {
    prompt: '"检查这个 Listing 的 IP 和认证风险"',
    steps: '读取内容版本 → 品牌与认证规则检查 → IP 风险初筛 → 引用官方政策依据',
  },
  {
    prompt: '"优化当前商品视频的分镜衔接"',
    steps: '读取视频模式与首帧 → 检查动作和镜头连续 → 优化提示词 → 预估积分后再生成',
  },
]

export const LANDING_VIDEO_MODES = [
  {
    id: 'marketing',
    title: '营销成片',
    desc: '给出商品和一个营销想法，Agent 自动生成创意、分镜并合成可投放成片。',
  },
  {
    id: 'storyboard',
    title: '专业分镜',
    desc: '粘贴完整脚本，逐镜锁定商品参考图、时长、动作衔接和画面风格。',
  },
  {
    id: 'single',
    title: '商品图生视频',
    desc: '一张商品图快速生成单镜头动态，适合主图视频、卖点展示和广告素材。',
  },
] as const

export const LANDING_VIDEO_STYLES = [
  '高端静奢',
  '真实生活',
  '电影叙事',
  '电商展示',
  '节日氛围',
  '参考图匹配',
] as const

export const FALLBACK_CREDIT_PACKS: LandingCreditPack[] = [
  { id: 'pack_trial_50', name: '首购体验包', credits: 50, price: 9.9, trial_once: true },
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
    monthly_credits: 3000,
    description: '适合工作室与专业卖家',
    validity_days: 30,
    recommended: true,
    features: [
      '每月 3,000 AI 积分',
      '所有 Standard 功能',
      '约 6 条 30 秒 768P 高质量营销成片',
      '约 660 张 AI 图片',
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
