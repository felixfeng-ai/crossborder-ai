import { getHeaderContext } from '@/lib/navigation'
import type { AgentActionIcon } from './workspace'

export interface AgentPageContext {
  route: string
  page: string
  details: string[]
  product_id?: string
  asset_id?: string
  asset_name?: string
  video_tab?: string
  campaign_id?: string
}

export interface AgentSidecarAction {
  label: string
  prompt: string
  icon: AgentActionIcon
}

const MAX_CONTEXT_DETAILS = 6
const MAX_DETAIL_LENGTH = 120

export function isAgentFullPage(pathname: string): boolean {
  return (
    pathname === '/app/agent' ||
    pathname.startsWith('/app/agent/') ||
    pathname === '/app/marketing-agent' ||
    pathname.startsWith('/app/marketing-agent/')
  )
}

export function deriveAgentPageContext(pathname: string): AgentPageContext {
  const header = getHeaderContext(pathname)
  return normalizeAgentPageContext({
    route: pathname,
    page: header.title,
    details: [],
  })
}

export function normalizeAgentPageContext(
  context: Partial<AgentPageContext>,
): AgentPageContext {
  const details = Array.from(
    new Set(
      (context.details || [])
        .map((item) => String(item || '').trim().slice(0, MAX_DETAIL_LENGTH))
        .filter(Boolean),
    ),
  ).slice(0, MAX_CONTEXT_DETAILS)

  return {
    route: String(context.route || '').trim().slice(0, 200),
    page: String(context.page || '').trim().slice(0, 80),
    details,
    product_id: cleanOptional(context.product_id),
    asset_id: cleanOptional(context.asset_id),
    asset_name: cleanOptional(context.asset_name, MAX_DETAIL_LENGTH),
    video_tab: cleanOptional(context.video_tab, 40),
    campaign_id: cleanOptional(context.campaign_id),
  }
}

export function buildAgentContextLabels(
  context: AgentPageContext,
): string[] {
  return Array.from(
    new Set(
      [context.page, ...context.details]
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  ).slice(0, MAX_CONTEXT_DETAILS + 1)
}

export function buildSidecarIntro(context: AgentPageContext): string {
  const detailText = context.details.length
    ? `已读取：${context.details.join('、')}。`
    : `已读取当前「${context.page}」。`

  if (context.route.startsWith('/app/images')) {
    return `${detailText}\n你可以问当前图片如何优化、检查平台主图要求，或继续生成白底图和商品视频。`
  }
  if (context.route.startsWith('/app/videos')) {
    return `${detailText}\n你可以让我优化镜头提示、检查首帧、估算积分，或继续处理当前视频任务。`
  }
  return `${detailText}\n直接告诉我你想判断、生成或执行什么，我会结合当前页面继续处理。`
}

export function buildSidecarQuickActions(
  context: AgentPageContext,
): AgentSidecarAction[] {
  if (context.route.startsWith('/app/images')) {
    return [
      {
        label: '分析当前图片',
        prompt: '分析当前图片工作台中选中的商品图片，指出平台适配、构图和质感问题。',
        icon: 'sparkles',
      },
      {
        label: '检查主图合规',
        prompt: '检查当前图片是否符合目标平台主图要求，并引用平台政策依据。',
        icon: 'file-text',
      },
      {
        label: '白底图建议',
        prompt: '根据当前图片和平台预设，给出白底图处理建议，先不要生成。',
        icon: 'image',
      },
      {
        label: '继续做视频',
        prompt: '基于当前选中的商品图片，给出商品图生视频方案和预计积分，先不要执行。',
        icon: 'clapperboard',
      },
    ]
  }
  if (context.route.startsWith('/app/videos')) {
    return [
      {
        label: '优化镜头提示',
        prompt: '结合当前视频模式和素材，优化镜头提示，保持商品外观和镜头连续性。',
        icon: 'sparkles',
      },
      {
        label: '检查首帧',
        prompt: '检查当前商品首帧是否适合生成视频，并给出具体修改建议。',
        icon: 'image',
      },
      {
        label: '估算积分',
        prompt: '根据当前视频模式、时长和质量档位估算本次生成积分，不要直接生成。',
        icon: 'file-text',
      },
      {
        label: '查看素材',
        prompt: '查看素材中心里适合当前视频任务的商品图片和视频。',
        icon: 'folder',
      },
    ]
  }
  return []
}

export function buildSidecarPlaceholder(context: AgentPageContext): string {
  if (context.route.startsWith('/app/images')) {
    return '询问当前图片、主图要求或下一步处理方式...'
  }
  if (context.route.startsWith('/app/videos')) {
    return '询问当前视频、镜头提示或生成前检查...'
  }
  return `询问当前「${context.page}」或直接描述下一步任务...`
}

function cleanOptional(value?: string, maxLength = 120): string | undefined {
  const normalized = String(value || '').trim().slice(0, maxLength)
  return normalized || undefined
}
