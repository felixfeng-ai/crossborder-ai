import { describe, expect, it } from 'vitest'

import {
  DEFAULT_THEME_MODE,
  readStoredThemeMode,
  resolveThemeMode,
} from '@/utils/themes'

describe('主题模式', () => {
  it('默认保持石墨主题', () => {
    expect(DEFAULT_THEME_MODE).toBe('graphite')
  })

  it('system 根据系统偏好解析石墨或白纸主题', () => {
    expect(resolveThemeMode('system', true)).toBe('graphite')
    expect(resolveThemeMode('system', false)).toBe('paper')
  })

  it('用户明确选择主题时不跟随系统变化', () => {
    expect(resolveThemeMode('harbor', true)).toBe('harbor')
    expect(resolveThemeMode('paper', true)).toBe('paper')
    expect(resolveThemeMode('graphite', false)).toBe('graphite')
  })

  it('缺失或非法本地主题回退到石墨', () => {
    expect(readStoredThemeMode(null)).toBe('graphite')
    expect(
      readStoredThemeMode({
        getItem: () => null,
      }),
    ).toBe('graphite')
    expect(
      readStoredThemeMode({
        getItem: () => 'invalid-theme',
      }),
    ).toBe('graphite')
    expect(
      readStoredThemeMode({
        getItem: () => 'paper',
      }),
    ).toBe('paper')
  })
})
