import { describe, expect, it } from 'vitest'
import {
  DEFAULT_LANGUAGE,
  LANGUAGE_DETECTION_ORDER,
  LANGUAGE_STORAGE_KEY,
  normalizeLanguageCode,
} from './language'


describe('language defaults', () => {
  it('首次进入默认使用中文，不跟随浏览器英文', () => {
    expect(DEFAULT_LANGUAGE).toBe('zh')
    expect(LANGUAGE_DETECTION_ORDER).toEqual(['localStorage'])
    expect(LANGUAGE_STORAGE_KEY).toBe('veyaship_language')
  })

  it('归一化浏览器语言标签并保留手动选择', () => {
    expect(normalizeLanguageCode('zh-CN')).toBe('zh')
    expect(normalizeLanguageCode('en-US')).toBe('en')
    expect(normalizeLanguageCode('unknown')).toBe('zh')
    expect(normalizeLanguageCode(null)).toBe('zh')
  })
})
