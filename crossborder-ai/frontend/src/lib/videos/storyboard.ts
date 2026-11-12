export interface StoryboardContinuity {
  global_constraints?: string
  no_dialogue?: boolean
  no_subtitles?: boolean
  no_watermark?: boolean
}

export function formatStoryboardTime(totalSeconds: number): string {
  const value = Math.max(0, Math.floor(totalSeconds || 0))
  const minutes = Math.floor(value / 60)
  const seconds = value % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function storyboardConstraintLabels(
  continuity: StoryboardContinuity,
): string[] {
  const labels: string[] = []
  if (continuity.no_dialogue) labels.push('无对白')
  if (continuity.no_subtitles) labels.push('无字幕')
  if (continuity.no_watermark) labels.push('无水印')
  return labels
}

export function storyboardSummary(shotCount: number, totalDuration: number): string {
  return `${shotCount} 个镜头 · ${totalDuration} 秒`
}
