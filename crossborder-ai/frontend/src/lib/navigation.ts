export type VideoWorkspaceTab = 'marketing' | 'storyboard' | 'single'

export const VIDEO_WORKSPACE_TABS: Array<{
  id: VideoWorkspaceTab
  label: string
}> = [
  { id: 'marketing', label: '营销成片' },
  { id: 'storyboard', label: '专业分镜' },
  { id: 'single', label: '商品图生视频' },
]

export interface NavigationItem {
  label: string
  path: string
}

export interface NavigationGroup {
  id: string
  label: string
  items: NavigationItem[]
}

export interface HeaderContext {
  group: string
  title: string
  description: string
}

export const NAVIGATION_GROUPS: NavigationGroup[] = [
  {
    id: 'operate',
    label: '经营',
    items: [
      { label: '仪表盘', path: '/app/dashboard' },
      { label: '商品库', path: '/app/products' },
      { label: 'Listing 中心', path: '/app/catalog' },
    ],
  },
  {
    id: 'create',
    label: 'AI 创作',
    items: [
      { label: 'AI 决策助手', path: '/app/agent' },
      { label: '营销 Agent', path: '/app/marketing-agent' },
      { label: '图片工作台', path: '/app/images' },
      { label: '视频工作台', path: '/app/videos' },
      { label: '素材中心', path: '/app/assets' },
    ],
  },
  {
    id: 'operations',
    label: '运营',
    items: [
      { label: '运营监控', path: '/app/operations' },
      { label: '渠道发布', path: '/app/shopify' },
    ],
  },
  {
    id: 'account',
    label: '账户',
    items: [
      { label: '使用教程', path: '/app/tutorial' },
      { label: '账单', path: '/app/billing' },
      { label: '设置', path: '/app/settings' },
    ],
  },
]

const HEADER_CONTEXTS: Record<string, HeaderContext> = {
  '/app/dashboard': {
    group: '经营',
    title: '仪表盘',
    description: '经营总览与待处理事项',
  },
  '/app/products': {
    group: '经营',
    title: '商品库',
    description: '来源商品、价格与商品资料',
  },
  '/app/catalog': {
    group: '经营',
    title: 'Listing 中心',
    description: 'SKU、Listing 与发布就绪状态',
  },
  '/app/content': {
    group: 'Listing 中心',
    title: 'AI Listing',
    description: '生成标题、描述、卖点与合规内容',
  },
  '/app/agent': {
    group: 'AI 创作',
    title: 'AI 决策助手',
    description: '先判断经营机会，再执行 Listing、合规与店铺任务',
  },
  '/app/marketing-agent': {
    group: 'AI 创作',
    title: '营销 Agent',
    description: '营销策略、图片、视频与文案',
  },
  '/app/images': {
    group: 'AI 创作',
    title: '图片工作台',
    description: '商品图片、白底图与平台尺寸',
  },
  '/app/videos': {
    group: 'AI 创作',
    title: '视频工作台',
    description: '营销成片与单镜头生成',
  },
  '/app/assets': {
    group: 'AI 创作',
    title: '素材中心',
    description: '统一管理和复用图片与视频素材',
  },
  '/app/operations': {
    group: '运营',
    title: '运营监控',
    description: 'SKU、库存与经营风险',
  },
  '/app/shopify': {
    group: '运营',
    title: '渠道发布',
    description: '店铺连接、Listing 发布与渠道状态',
  },
  '/app/billing': {
    group: '账户',
    title: '账单',
    description: '套餐、积分与付款记录',
  },
  '/app/tutorial': {
    group: '账户',
    title: '使用教程',
    description: '从商品录入到发布与巡检的完整操作指南',
  },
  '/app/settings': {
    group: '账户',
    title: '设置',
    description: '品牌、平台连接与服务商配置',
  },
  '/app/admin/upgrades': {
    group: '账户',
    title: '升级审核',
    description: '管理员套餐申请审核',
  },
}

export function getHeaderContext(pathname: string): HeaderContext {
  if (HEADER_CONTEXTS[pathname]) return HEADER_CONTEXTS[pathname]
  if (pathname.startsWith('/app/products/')) {
    return {
      group: '经营',
      title: '商品详情',
      description: '商品资料、Listing 与渠道状态',
    }
  }
  return {
    group: 'VeyaShip',
    title: '一体化 AI 运营台',
    description: '从选品判断到合规上架',
  }
}

export function videoTabFromSearch(search: string): VideoWorkspaceTab {
  const tab = new URLSearchParams(search).get('tab')
  if (tab === 'storyboard') return 'storyboard'
  return tab === 'single' ? 'single' : 'marketing'
}
