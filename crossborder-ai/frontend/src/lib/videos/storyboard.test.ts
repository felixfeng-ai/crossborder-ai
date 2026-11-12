import { describe, expect, it } from 'vitest'
import {
  formatStoryboardTime,
  storyboardConstraintLabels,
  storyboardSummary,
} from './storyboard'


describe('professional storyboard helpers', () => {
  it('格式化分镜时间轴', () => {
    expect(formatStoryboardTime(0)).toBe('00:00')
    expect(formatStoryboardTime(65)).toBe('01:05')
  })

  it('展示脚本约束', () => {
    expect(
      storyboardConstraintLabels({
        no_dialogue: true,
        no_subtitles: true,
        no_watermark: true,
      }),
    ).toEqual(['无对白', '无字幕', '无水印'])
  })

  it('汇总分镜数量和总时长', () => {
    expect(storyboardSummary(8, 30)).toBe('8 个镜头 · 30 秒')
  })
})
