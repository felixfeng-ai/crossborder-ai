import { create } from 'zustand'

import {
  DEFAULT_THEME_MODE,
  THEME_STORAGE_KEY,
  applyThemeMode,
  isThemeMode,
  persistThemeMode,
  readStoredThemeMode,
  resolveThemeMode,
  type ResolvedTheme,
  type ThemeMode,
} from '@/utils/themes'

type ThemeStore = {
  mode: ThemeMode
  resolved: ResolvedTheme
  setMode: (mode: ThemeMode) => void
  syncSystemTheme: () => void
  syncStoredTheme: () => void
}

const initialMode =
  typeof document === 'undefined'
    ? DEFAULT_THEME_MODE
    : (() => {
        const bootMode = document.documentElement.dataset.themeMode
        const candidate = bootMode || null
        return isThemeMode(candidate) ? candidate : DEFAULT_THEME_MODE
      })()

export const useThemeStore = create<ThemeStore>((set, get) => ({
  mode: initialMode,
  resolved:
    typeof document !== 'undefined' && document.documentElement.dataset.theme
      ? (document.documentElement.dataset.theme as ResolvedTheme)
      : resolveThemeMode(initialMode, true),

  setMode: (mode) => {
    persistThemeMode(mode)
    const resolved = applyThemeMode(mode)
    set({ mode, resolved })
  },

  syncSystemTheme: () => {
    if (get().mode !== 'system') return
    const resolved = applyThemeMode('system')
    set({ resolved })
  },

  syncStoredTheme: () => {
    const mode = readStoredThemeMode(window.localStorage)
    const resolved = applyThemeMode(mode)
    set({ mode, resolved })
  },
}))

let themeListenersBound = false

/**
 * 在 React 渲染前接管 index.html 的主题结果，并监听系统主题和多标签页变化。
 */
export function bootstrapTheme() {
  const mode = readStoredThemeMode(window.localStorage)
  const resolved = applyThemeMode(mode)
  useThemeStore.setState({ mode, resolved })

  if (themeListenersBound) return { mode, resolved }
  themeListenersBound = true

  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const handleSystemChange = () => {
    useThemeStore.getState().syncSystemTheme()
  }
  const handleStorage = (event: StorageEvent) => {
    if (event.key !== THEME_STORAGE_KEY) return
    useThemeStore.getState().syncStoredTheme()
  }

  media.addEventListener?.('change', handleSystemChange)
  window.addEventListener('storage', handleStorage)
  return { mode, resolved }
}
