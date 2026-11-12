import type { VideoQualityTier, VideoStylePreset } from './quality'

export interface VideoModelCapability {
  id: string
  min_duration: number
  max_duration: number
  resolutions: string[]
  prices_per_second: Record<string, number>
  credits_per_second: Record<string, number>
}

export interface VideoTemplate {
  id: string
  name: string
  description: string
  prompt_suffix: string
}

export interface VideoCapabilities {
  enabled: boolean
  provider: string
  default_model: string
  default_resolution: string
  models: VideoModelCapability[]
  templates: VideoTemplate[]
  quality_tiers: VideoQualityTier[]
  style_presets: VideoStylePreset[]
}

export interface VideoTask {
  id: string
  status: string
  video_url?: string | null
  thumbnail_url?: string | null
  model: string
  resolution: string
  provider: string
  quality_tier: string
  style_preset: string
  credits_per_second: number
  duration: number
  ratio: string
  prompt: string
  error?: string | null
  credits_cost: number
  created_at: string
  finished_at?: string | null
}

const STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '生成中',
  succeeded: '已完成',
  failed: '生成失败',
  canceled: '已取消',
}

const TERMINAL_STATES = new Set(['succeeded', 'failed', 'canceled'])

export function getVideoModel(
  capabilities: VideoCapabilities | undefined,
  modelId: string,
): VideoModelCapability | undefined {
  return capabilities?.models.find((model) => model.id === modelId)
}

/**
 * 前端估算必须与后端积分保护一致：按秒单价累计。
 */
export function estimateVideoCredits(
  capabilities: VideoCapabilities | undefined,
  modelId: string,
  resolution: string,
  duration: number,
): number {
  const model = getVideoModel(capabilities, modelId)
  const perSecond = model?.credits_per_second?.[resolution]
  if (!perSecond) return 0
  return Math.max(1, Math.ceil(perSecond * duration))
}

export function isVideoTerminal(status: string): boolean {
  return TERMINAL_STATES.has(status)
}

export function videoStatusLabel(status: string): string {
  return STATUS_LABELS[status] || '处理中'
}

export function formatVideoDuration(duration: number): string {
  return `${duration} 秒`
}
