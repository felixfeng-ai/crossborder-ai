export type TutorialStepId =
  | 'product'
  | 'assistant'
  | 'listing'
  | 'media'
  | 'publish'
  | 'account'

export interface TutorialAction {
  label: string
  path: string
  description?: string
}

export interface TutorialStep {
  id: TutorialStepId
  step: string
  title: string
  summary: string
  outcomes: string[]
  actions: TutorialAction[]
}

export interface TutorialQuickLink {
  label: string
  path: string
  description: string
}

export const TUTORIAL_QUICK_LINKS: TutorialQuickLink[] = [
  {
    label: '录入第一个商品',
    path: '/app/products',
    description: '从 1688、CSV 或自有货源开始',
  },
  {
    label: '咨询 AI 决策助手',
    path: '/app/agent',
    description: '判断市场、利润和下一步动作',
  },
  {
    label: '处理商品图片',
    path: '/app/images',
    description: '上传、白底图与平台尺寸',
  },
  {
    label: '生成商品视频',
    path: '/app/videos?tab=single',
    description: '商品图生视频或营销成片',
  },
]

export const TUTORIAL_STEPS: TutorialStep[] = [
  {
    id: 'product',
    step: '01',
    title: '先把商品事实录入商品库',
    summary:
      '商品库是所有 AI 判断、Listing、图片和渠道任务的共同事实源。先确认标题、供货价、图片和来源链接，再进入后续步骤。',
    outcomes: [
      '支持 1688 商品链接、CSV 批量导入和自有货源手动录入',
      '商品原图会进入图片工作台，并可继续处理白底图和平台尺寸',
      '后续 Agent、Listing 和发布任务都复用同一商品记录',
    ],
    actions: [
      {
        label: '进入商品库',
        path: '/app/products',
        description: '新增、导入或检查商品资料',
      },
    ],
  },
  {
    id: 'assistant',
    step: '02',
    title: '在任何工作台随时问 AI',
    summary:
      '右下角“问 AI”会在当前页面打开 AI 决策助手，不需要离开图片台或视频台。侧栏会带入当前页面、素材和视频模式。',
    outcomes: [
      '桌面快捷键 Alt + A 可以打开或关闭侧栏',
      '图片工作台会带入当前素材和平台预设',
      '视频工作台会带入营销成片、专业分镜或商品图生视频模式',
      '关闭侧栏不会取消正在执行的 Agent 任务，重新打开可继续查看',
    ],
    actions: [
      {
        label: '打开完整 AI 决策助手',
        path: '/app/agent',
        description: '适合长对话、复杂报告和历史任务',
      },
      {
        label: '从图片工作台开始',
        path: '/app/images',
        description: '在当前素材旁直接咨询',
      },
    ],
  },
  {
    id: 'listing',
    step: '03',
    title: '生成 Listing，同时完成合规与风险初筛',
    summary:
      'Listing 中心负责标题、卖点、描述、SKU 和发布就绪状态。生成内容后继续执行合规审查、IP 风险初筛和平台政策检索。',
    outcomes: [
      '合规检查覆盖违禁词、极限词、品牌禁词和认证声称',
      'IP 风险初筛提示商标、授权链、影视或卡通形象等风险',
      '政策知识库提供 Amazon、TikTok Shop 和 Shopify 的官方依据',
    ],
    actions: [
      {
        label: '打开 Listing 中心',
        path: '/app/catalog',
        description: '查看 SKU、内容和发布状态',
      },
      {
        label: '让 Agent 生成或回查 Listing',
        path: '/app/agent',
        description: '先判断商品，再生成和检查内容',
      },
    ],
  },
  {
    id: 'media',
    step: '04',
    title: '完成图片、视频和营销素材',
    summary:
      '图片工作台负责上传、素材库、平台尺寸和白底图；视频工作台统一营销成片、专业分镜和商品图生视频。',
    outcomes: [
      '图片任务支持上传进度、成功提示和素材删除',
      '视频任务支持多参考图、风格选择、生成进度和封面记录',
      '生成结果沉淀到素材中心，可继续查询和复用',
    ],
    actions: [
      {
        label: '进入图片工作台',
        path: '/app/images',
        description: '上传、白底和平台尺寸',
      },
      {
        label: '进入视频工作台',
        path: '/app/videos',
        description: '营销成片、专业分镜和商品图生视频',
      },
      {
        label: '查看素材中心',
        path: '/app/assets',
        description: '统一管理已生成的图片和视频',
      },
    ],
  },
  {
    id: 'publish',
    step: '05',
    title: '连接渠道，发布并持续巡检',
    summary:
      '准备好商品和内容后，在渠道发布中连接店铺并检查发布边界。运营监控会按 SKU 检查库存、毛利和经营异常。',
    outcomes: [
      'Shopify 支持草稿发布和运营同步',
      'Amazon 通过 SP-API 提供 Listing 发布能力',
      '运营监控汇总库存、补货点、毛利和待处理风险',
    ],
    actions: [
      {
        label: '进入渠道发布',
        path: '/app/shopify',
        description: '连接店铺并检查发布状态',
      },
      {
        label: '打开运营监控',
        path: '/app/operations',
        description: '查看 SKU 和经营待办',
      },
    ],
  },
  {
    id: 'account',
    step: '06',
    title: '管理积分、自动化和工作偏好',
    summary:
      '图片、视频、Agent 和批量任务会按功能扣减积分。设置页可以控制自动任务开关，账单页可查看套餐、购买积分和扣费记录。',
    outcomes: [
      '套餐积分按月发放，购买积分独立保留',
      '自动化任务可通过开关启用或暂停',
      '高成本操作在执行前应确认模式和预计积分',
    ],
    actions: [
      {
        label: '查看账单与积分',
        path: '/app/billing',
        description: '套餐、积分包和消费记录',
      },
      {
        label: '打开设置',
        path: '/app/settings',
        description: '自动化、品牌和平台配置',
      },
    ],
  },
]

export const TUTORIAL_SHORTCUTS = [
  {
    keys: 'Alt + A',
    description: '在当前页面打开或关闭 AI 决策助手',
  },
  {
    keys: 'Esc',
    description: '关闭 AI 助手侧栏并把焦点返回入口',
  },
] as const
