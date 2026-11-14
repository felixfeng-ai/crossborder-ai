/**
 * VeyaShip 主题模式。
 * graphite 继续作为默认品牌主题，paper 与 harbor 仅在用户主动选择后生效。
 */
export const THEME_STORAGE_KEY = 'veya-theme'
export const DEFAULT_THEME_MODE = 'graphite' as const

export type ThemeMode = 'graphite' | 'paper' | 'harbor' | 'system'
export type ResolvedTheme = Exclude<ThemeMode, 'system'>

type StorageLike = {
  getItem: (key: string) => string | null
}

export type ThemeOption = {
  value: ThemeMode
  label: string
  description: string
  swatches: [string, string, string, string]
}

export const THEME_OPTIONS: ThemeOption[] = [
  {
    value: 'graphite',
    label: '石墨琥珀',
    description: '默认主题，适合 AI 创作与夜间运营',
    swatches: ['#0d0e0e', '#151615', '#f3f2ed', '#d8b56d'],
  },
  {
    value: 'paper',
    label: '纯白纸张',
    description: '高对比白色工作台，适合白天和通用运营',
    swatches: ['#ffffff', '#f7f7f4', '#171815', '#9a6918'],
  },
  {
    value: 'harbor',
    label: '海港青',
    description: '适合物流、合规和多平台渠道运营',
    swatches: ['#f2f7f7', '#ffffff', '#102426', '#16696c'],
  },
  {
    value: 'system',
    label: '跟随系统',
    description: '深色使用石墨，浅色使用纯白纸张',
    swatches: ['#0d0e0e', '#ffffff', '#d8b56d', '#9a6918'],
  },
]

const VALID_THEME_MODES = new Set<ThemeMode>([
  'graphite',
  'paper',
  'harbor',
  'system',
])

export function isThemeMode(value: string | null): value is ThemeMode {
  return value !== null && VALID_THEME_MODES.has(value as ThemeMode)
}

/**
 * 只有用户主动选择 system 时才跟随系统深浅色。
 */
export function resolveThemeMode(
  mode: ThemeMode,
  prefersDark: boolean,
): ResolvedTheme {
  if (mode === 'system') return prefersDark ? 'graphite' : 'paper'
  return mode
}

export function readStoredThemeMode(storage: StorageLike | null): ThemeMode {
  if (!storage) return DEFAULT_THEME_MODE
  try {
    const value = storage.getItem(THEME_STORAGE_KEY)
    return isThemeMode(value) ? value : DEFAULT_THEME_MODE
  } catch {
    return DEFAULT_THEME_MODE
  }
}

export function getSystemPrefersDark(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return true
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function applyThemeMode(mode: ThemeMode): ResolvedTheme {
  const resolved = resolveThemeMode(mode, getSystemPrefersDark())
  if (typeof document === 'undefined') return resolved

  const root = document.documentElement
  root.dataset.theme = resolved
  root.dataset.themeMode = mode
  root.classList.toggle('dark', resolved === 'graphite')
  root.style.colorScheme = resolved === 'graphite' ? 'dark' : 'light'

  const themeColor = resolved === 'graphite' ? '#0d0e0e' : '#ffffff'
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', themeColor)
  return resolved
}

export function persistThemeMode(mode: ThemeMode) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, mode)
  } catch {
    // 隐私模式可能禁用 storage，主题仍可在当前会话生效。
  }
}

export function initTheme() {
  const mode = readStoredThemeMode(
    typeof window === 'undefined' ? null : window.localStorage,
  )
  const resolved = applyThemeMode(mode)
  return { mode, resolved }
}
