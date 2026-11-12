import type { VideoQualityTier, VideoStylePreset } from './quality'

export interface MarketingVideoBrief {
  title?: string
  audience?: string
  angle?: string
  hook?: string
  script?: string
  cta?: string
  shots?: MarketingVideoShot[]
}

export interface MarketingVideoShot {
  position: number
  title: string
  purpose: string
  prompt: string
  source_text?: string | null
  start_seconds?: number
  end_seconds?: number
  duration: number
  status: string
  video_url?: string | null
  error?: string | null
}

export interface MarketingProductReference {
  asset_id: string
  role: string
  is_primary: boolean
}

export interface MarketingVideoProject {
  id: string
  title: string
  product_name: string
  idea: string
  platform: string
  market: string
  language: string
  duration: number
  template_id: string
  mode?: 'creative' | 'script' | string
  reference_assets?: MarketingProductReference[]
  continuity_mode?: 'natural' | string
  quality_tier?: string
  style_preset?: string
  credits_per_second?: number
  script_text?: string | null
  continuity?: Record<string, unknown>
  model: string
  resolution: string
  status: string
  brief: MarketingVideoBrief
  shots: MarketingVideoShot[]
  credits_estimated: number
  credits_charged: number
  credits_refunded?: number
  video_available?: boolean
  final_video_url?: string | null
  thumbnail_url?: string | null
  subtitle_url?: string | null
  subtitles_burned_in?: boolean
  error?: string | null
  created_at: string
  finished_at?: string | null
}

export interface MarketingTemplate {
  id: string
  name: string
  description: string
}

export interface MarketingPlatform {
  id: string
  name: string
  ratio: string
}

export interface MarketingCapabilities {
  enabled: boolean
  provider: string
  default_model: string
  default_resolution: string
  models: Array<{
    id: string
    min_duration: number
    max_duration: number
    resolutions: string[]
    credits_per_second: Record<string, number>
  }>
  platforms: MarketingPlatform[]
  marketing_templates: MarketingTemplate[]
  durations: number[]
  quality_tiers: VideoQualityTier[]
  style_presets: VideoStylePreset[]
  voice?: {
    enabled: boolean
    provider: string
    reason: string
    model: string
    voice_id: string
  }
}

export interface MarketingPipelineStep {
  id: 'brief' | 'shots' | 'assembly'
  label: string
  state: 'complete' | 'current' | 'pending' | 'failed'
}

const PROJECT_STATUS_LABELS: Record<string, string> = {
  brief_ready: '待审阅',
  rendering: '生成中',
  succeeded: '已完成',
  failed: '生成失败',
  canceled: '已取消',
}

const SHOT_STATUS_LABELS: Record<string, string> = {
  planned: '等待审批',
  queued: '排队中',
  running: '生成中',
  succeeded: '已完成',
  failed: '生成失败',
  canceled: '已取消',
}

const TEMPLATE_NAMES: Record<string, string> = {
  presenter_demo: '人物演示',
  problem_solution: '痛点解决',
  unboxing: '开箱展示',
  feature_focus: '卖点聚焦',
  professional_script: '专业脚本分镜',
}

export function projectStatusLabel(status: string): string {
  return PROJECT_STATUS_LABELS[status] || '处理中'
}

export function shotStatusLabel(status: string): string {
  return SHOT_STATUS_LABELS[status] || '处理中'
}

export function marketingTemplateName(templateId: string): string {
  return TEMPLATE_NAMES[templateId] || '营销模板'
}

export function totalShotDuration(shots: MarketingVideoShot[]): number {
  return shots.reduce((total, shot) => total + Math.max(0, shot.duration), 0)
}

export interface MarketingRenderProgress {
  completed: number
  total: number
  percent: number
  label: string
  detail: string
}

export function marketingRenderProgress(
  project: MarketingVideoProject,
): MarketingRenderProgress {
  const total = project.shots.length
  const completed = project.shots.filter((shot) => shot.status === 'succeeded').length
  const running = project.shots.filter((shot) => shot.status === 'running').length
  if (project.status === 'succeeded') {
    return {
      completed,
      total,
      percent: 100,
      label: '成片已完成',
      detail: '视频文件已经可以预览和下载',
    }
  }
  if (project.status === 'failed' || project.status === 'canceled') {
    return {
      completed,
      total,
      percent: total > 0 ? Math.round((completed / total) * 88) : 0,
      label: project.status === 'failed' ? '生成失败' : '生成已取消',
      detail: project.error || `已完成 ${completed}/${total} 个镜头`,
    }
  }
  if (project.status !== 'rendering') {
    return {
      completed,
      total,
      percent: 0,
      label: '等待生成',
      detail: '确认方案后开始生成分镜',
    }
  }
  if (total > 0 && completed === total) {
    return {
      completed,
      total,
      percent: 94,
      label: '正在合成成片',
      detail: '镜头已完成，正在处理转场、音轨和视频文件',
    }
  }
  return {
    completed,
    total,
    percent: total > 0 ? Math.round((completed / total) * 88) : 0,
    label: '分镜生成中',
    detail: running > 0
      ? `已完成 ${completed}/${total} 个镜头，${running} 个正在生成`
      : `已完成 ${completed}/${total} 个镜头，等待下一批任务`,
  }
}

/** 清理商品名中的系统非法字符，生成可跨平台下载的文件名。 */
export function safeFilenamePart(value: string, fallback: string): string {
  const cleaned = String(value || '')
    .normalize('NFKC')
    .replace(/[\\/:*?"<>|\u0000-\u001f]/g, '-')
    .replace(/\s*-\s*/g, '-')
    .replace(/\s+/g, ' ')
    .replace(/^[- .]+|[- .]+$/g, '')
    .slice(0, 80)
  return cleaned || fallback
}

export function estimateVoiceoverCredits(brief: MarketingVideoBrief): number {
  const text = [brief.hook, brief.script, brief.cta]
    .map((value) => String(value || '').trim())
    .filter(Boolean)
    .join(' ')
  return Math.max(3, Math.ceil(text.length / 100))
}

export function downloadFilename(
  project: MarketingVideoProject,
  extension: 'mp4' | 'srt' | 'mp3',
): string {
  const product = safeFilenamePart(
    project.product_name || project.title,
    '商品视频',
  )
  const platform = safeFilenamePart(project.platform, 'video')
  const labels = {
    mp4: '营销成片',
    srt: '营销成片字幕',
    mp3: 'AI配音',
  }
  return `${product}-${platform}-${labels[extension]}.${extension}`
}

export function buildMarketingPipeline(
  project: MarketingVideoProject,
): MarketingPipelineStep[] {
  const failed = project.status === 'failed' || project.status === 'canceled'
  const briefLabel = project.mode === 'script' ? '脚本文案' : '营销方案'
  if (project.status === 'brief_ready') {
    return [
      { id: 'brief', label: briefLabel, state: 'current' },
      { id: 'shots', label: '分镜生成', state: 'pending' },
      { id: 'assembly', label: '成片合成', state: 'pending' },
    ]
  }
  if (project.status === 'rendering') {
    return [
      { id: 'brief', label: briefLabel, state: 'complete' },
      { id: 'shots', label: '分镜生成', state: 'current' },
      { id: 'assembly', label: '成片合成', state: 'pending' },
    ]
  }
  if (project.status === 'succeeded') {
    return [
      { id: 'brief', label: briefLabel, state: 'complete' },
      { id: 'shots', label: '分镜生成', state: 'complete' },
      { id: 'assembly', label: '成片合成', state: 'complete' },
    ]
  }
  return [
    { id: 'brief', label: briefLabel, state: 'complete' },
    { id: 'shots', label: '分镜生成', state: failed ? 'failed' : 'current' },
    { id: 'assembly', label: '成片合成', state: failed ? 'pending' : 'current' },
  ]
}
