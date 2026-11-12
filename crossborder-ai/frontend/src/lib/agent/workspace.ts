export type AgentWorkspaceMode = 'general' | 'marketing'

export type AgentActionIcon =
  | 'shopping-cart'
  | 'file-text'
  | 'image'
  | 'sparkles'
  | 'clapperboard'
  | 'folder'
  | 'megaphone'

export interface AgentQuickAction {
  label: string
  prompt: string
  icon: AgentActionIcon
}

export interface AgentWorkspaceDefinition {
  label: string
  intro: string
  placeholder: string
  footer: string
  actions: AgentQuickAction[]
}

export const AGENT_WORKSPACES: Record<
  AgentWorkspaceMode,
  AgentWorkspaceDefinition
> = {
  general: {
    label: 'AI 决策助手',
    intro: [
      '我是 VeyaShip AI 决策助手。',
      '',
      '先判断商品和市场值不值得做，再把 Listing、素材、合规和上架任务继续执行下去。',
      '',
      '你可以直接告诉我：',
      '- **选品与利润**：分析品类、测算净利',
      '- **Listing**：生成、回查、修改文案',
      '- **商品素材**：生成图片、查询素材、提交商品视频',
      '- **店铺执行**：合规检查、订单同步与发布',
      '',
      '给我商品链接、目标平台，或者直接描述当前经营问题。',
    ].join('\n'),
    placeholder: '粘贴 1688 链接，或描述要判断、生成和执行的经营任务...',
    footer: '先判断，再把 Listing、素材、合规与上架任务执行下去',
    actions: [
      {
        label: 'AI 选品',
        prompt: '帮我分析一个适合美国市场的跨境品类，并推荐值得做的方向',
        icon: 'shopping-cart',
      },
      {
        label: '生成 Listing',
        prompt: '帮我基于商品库中的商品生成 Amazon Listing，英文',
        icon: 'file-text',
      },
      {
        label: '商品图片',
        prompt: '帮我基于商品信息生成一张高质量商品主图',
        icon: 'image',
      },
      {
        label: '商品图生视频',
        prompt: '帮我基于素材中心中的商品首帧生成商品视频，先告诉我预计积分',
        icon: 'clapperboard',
      },
      {
        label: '查看素材',
        prompt: '查看我最新的图片、商品视频和营销视频项目',
        icon: 'folder',
      },
    ],
  },
  marketing: {
    label: '营销 Agent',
    intro: [
      '你好，我是 VeyaShip 营销 Agent。',
      '',
      '我会围绕一个商品和目标市场，把营销策略、图片、视频和文案串成同一项活动：',
      '- **营销方案**：目标人群、卖点、渠道和素材清单',
      '- **营销图片**：商品主图、生活场景图和广告图',
      '- **营销视频**：分镜方案、积分预估和成片',
      '- **广告文案**：标题、卖点、CTA 和平台适配',
      '',
      '告诉我商品和营销目标即可开始。',
    ].join('\n'),
    placeholder: '描述商品、营销目标、平台、折扣或目标人群...',
    footer: '营销 Agent 会组合营销图片、商品视频、广告文案与素材资产',
    actions: [
      {
        label: '营销方案',
        prompt:
          '读取商品库中最近的商品，围绕目标平台制定一套包含营销图片、短视频和广告文案的活动方案，先展示预计积分。',
        icon: 'file-text',
      },
      {
        label: '商品主图',
        prompt:
          '基于商品库中最近的商品生成一张高转化商品主图，保留商品外观、材质、Logo 和包装文字，先说明预计积分。',
        icon: 'image',
      },
      {
        label: '场景营销图',
        prompt:
          '基于商品参考图生成一张真实生活场景营销图，先说明选择哪个商品、目标平台和预计积分。',
        icon: 'sparkles',
      },
      {
        label: '营销视频',
        prompt:
          '基于商品素材制定一条 15 秒营销视频的方案和分镜，确认后再渲染，优先调用营销视频工具。',
        icon: 'clapperboard',
      },
      {
        label: '广告文案',
        prompt:
          '基于商品信息和目标市场生成 TikTok、Amazon 和 Shopify 可复用的广告文案、卖点和 CTA。',
        icon: 'megaphone',
      },
    ],
  },
}

export function agentWorkspaceCopy(mode: AgentWorkspaceMode) {
  const workspace = AGENT_WORKSPACES[mode]
  return {
    label: workspace.label,
    intro: workspace.intro,
    placeholder: workspace.placeholder,
    footer: workspace.footer,
    actions: workspace.actions,
  }
}
