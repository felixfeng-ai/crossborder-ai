export const DEFAULT_LANGUAGE = 'zh' as const

export const LANGUAGE_DETECTION_ORDER = ['localStorage'] as const
export const LANGUAGE_STORAGE_KEY = 'veyaship_language'

export const SUPPORTED_LANGUAGE_CODES = [
  'en',
  'zh',
  'ja',
  'ko',
  'es',
  'fr',
  'de',
  'pt',
  'ru',
] as const

export function normalizeLanguageCode(value: string | null | undefined): string {
  const base = String(value || '').toLowerCase().split('-')[0]
  return SUPPORTED_LANGUAGE_CODES.includes(
    base as (typeof SUPPORTED_LANGUAGE_CODES)[number],
  )
    ? base
    : DEFAULT_LANGUAGE
}
