import { describe, expect, it } from 'vitest'
import { dominantSentiment, sentimentLabel } from './voc'


describe('VOC helpers', () => {
  it('展示最高占比情感并归一化百分比', () => {
    const sentiment = { positive: 0.6, neutral: 0.2, negative: 0.2 }
    expect(dominantSentiment(sentiment)).toBe('positive')
    expect(sentimentLabel('positive')).toBe('正向')
  })

  it('兼容历史百分比和归一化数值', () => {
    expect(dominantSentiment({ positive: 62, neutral: 23, negative: 15 })).toBe(
      'positive',
    )
    expect(dominantSentiment({})).toBe('neutral')
  })
})
