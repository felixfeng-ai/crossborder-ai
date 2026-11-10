export type ListingContentFormat = 'html' | 'markdown' | 'plain'

export interface ParsedListingDescription {
  shortDescription: string
  detailMarkdown: string
  detailHtml: string
  format: ListingContentFormat
  source: string
}

type SectionName = 'title' | 'short' | 'detail'

const SECTION_MARKERS: Array<{ name: SectionName; patterns: string[] }> = [
  { name: 'title', patterns: ['商品标题', 'product title'] },
  { name: 'short', patterns: ['简短描述', 'short description'] },
  { name: 'detail', patterns: ['商品详情描述', '详细描述', 'product description', 'detail description'] },
]

/**
 * 兼容历史 AI 输出：旧结果会把标题、简短描述和详情塞进同一个字符串。
 * 新结果即使只有详情，也会走同一解析路径。
 */
export function parseListingDescription(raw: string): ParsedListingDescription {
  const source = raw || ''
  const sections = splitLegacySections(source)
  const detail = sections.detail || (sections.hasLegacySections ? '' : source.trim())
  const extractedHtml = extractFencedHtml(detail)
  const shortDescription = stripMarkup(sections.short)

  if (extractedHtml) {
    return {
      shortDescription,
      detailMarkdown: stripFence(detail),
      detailHtml: extractedHtml,
      format: 'html',
      source,
    }
  }

  if (looksLikeHtml(detail)) {
    return {
      shortDescription,
      detailMarkdown: detail.trim(),
      detailHtml: detail.trim(),
      format: 'html',
      source,
    }
  }

  return {
    shortDescription,
    detailMarkdown: detail.trim(),
    detailHtml: '',
    format: looksLikeMarkdown(detail) ? 'markdown' : 'plain',
    source,
  }
}

function splitLegacySections(raw: string): {
  title: string
  short: string
  detail: string
  hasLegacySections: boolean
} {
  const buckets: Record<SectionName, string[]> = {
    title: [],
    short: [],
    detail: [],
  }
  let current: SectionName | null = null
  let hasLegacySections = false

  for (const line of raw.replace(/\r\n/g, '\n').split('\n')) {
    const heading = line.match(/^#{1,6}\s+(.+?)\s*$/)
    if (heading) {
      const matched = matchSectionMarker(heading[1])
      if (matched) {
        current = matched
        hasLegacySections = true
        continue
      }
    }

    if (current && !isSeparator(line)) {
      buckets[current].push(line)
    }
  }

  return {
    title: buckets.title.join('\n').trim(),
    short: buckets.short.join('\n').trim(),
    detail: buckets.detail.join('\n').trim(),
    hasLegacySections,
  }
}

function matchSectionMarker(heading: string): SectionName | null {
  const normalized = heading.toLowerCase()
  for (const section of SECTION_MARKERS) {
    if (section.patterns.some((pattern) => normalized.includes(pattern.toLowerCase()))) {
      return section.name
    }
  }
  return null
}

function isSeparator(line: string): boolean {
  return /^\s*-{3,}\s*$/.test(line)
}

function extractFencedHtml(value: string): string {
  const match = value.match(/```(?:html)?\s*([\s\S]*?)```/i)
  return match?.[1]?.trim() || ''
}

function stripFence(value: string): string {
  return value.replace(/```(?:html)?\s*([\s\S]*?)```/i, '$1').trim()
}

function looksLikeHtml(value: string): boolean {
  return /<(?:h[1-6]|p|ul|ol|li|strong|em|br|table|thead|tbody|tr|th|td)\b[^>]*>/i.test(value)
}

function looksLikeMarkdown(value: string): boolean {
  return /^(?:#{1,6}\s|[-*]\s|\d+\.\s)|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)/m.test(value)
}

function stripMarkup(value: string): string {
  return value
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[*_~`#>-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}
