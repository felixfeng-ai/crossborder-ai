export type VocSentiment = 'positive' | 'neutral' | 'negative'

const SENTIMENT_LABELS: Record<VocSentiment, string> = {
  positive: '正向',
  neutral: '中性',
  negative: '负向',
}

export function sentimentLabel(value: VocSentiment): string {
  return SENTIMENT_LABELS[value] || '中性'
}

export function dominantSentiment(
  sentiment: Record<string, unknown> | null | undefined,
): VocSentiment {
  if (!sentiment) return 'neutral'
  const candidates: VocSentiment[] = ['positive', 'neutral', 'negative']
  let dominant: VocSentiment = 'neutral'
  let highest = 0
  for (const candidate of candidates) {
    const parsed = Number(sentiment[candidate])
    const score = Number.isFinite(parsed) ? parsed : 0
    if (score > highest) {
      highest = score
      dominant = candidate
    }
  }
  return dominant
}

export function sentimentPercent(
  sentiment: Record<string, unknown> | null | undefined,
  key: VocSentiment,
): number {
  const raw = Number(sentiment?.[key] || 0)
  if (!Number.isFinite(raw)) return 0
  return Math.max(0, Math.min(100, Math.round(raw <= 1 ? raw * 100 : raw)))
}
