/**
 * VeyaShip 石墨决策台主题。
 *
 * 平台只保留一个正式方向，避免历史多主题在字体、光效和圆角上产生漂移。
 * 主题变量的语义名称保持不变，页面组件不需要感知具体色值。
 */
export interface Theme {
  name: 'graphite'
  label: string
  colors: Record<string, string>
}

export const themes: Theme[] = [
  {
    name: 'graphite',
    label: '石墨',
    colors: {
      '--background': '120 4% 5%',
      '--foreground': '50 20% 94%',
      '--card': '120 2% 8%',
      '--card-foreground': '50 20% 94%',
      '--popover': '100 4% 11%',
      '--popover-foreground': '50 20% 94%',
      '--primary': '50 20% 94%',
      '--primary-foreground': '120 4% 5%',
      '--secondary': '120 2% 10%',
      '--secondary-foreground': '50 12% 88%',
      '--muted': '120 2% 9%',
      '--muted-foreground': '40 8% 68%',
      '--accent': '100 7% 12%',
      '--accent-foreground': '50 18% 90%',
      '--destructive': '14 57% 65%',
      '--destructive-foreground': '120 4% 5%',
      '--border': '90 5% 16%',
      '--input': '90 5% 18%',
      '--ring': '40 58% 64%',
      '--factory-ground': '#0d0e0e',
      '--factory-side': '#101110',
      '--factory-panel': '#151615',
      '--factory-raised': '#1b1c1a',
      '--factory-line': 'rgba(243, 242, 237, 0.09)',
      '--factory-line-strong': 'rgba(243, 242, 237, 0.16)',
      '--factory-ink': '#f3f2ed',
      '--factory-muted': '#b4b0a8',
      '--factory-faint': '#8f8c85',
      '--factory-accent': '#d8b56d',
      '--factory-mint': '#9dbbad',
      '--factory-coral': '#d98b70',
    },
  },
]

export function getTheme(): Theme {
  return themes[0]
}

export function applyTheme(theme: Theme = themes[0]) {
  if (typeof window === 'undefined') return

  localStorage.setItem('veya-theme', theme.name)
  const root = document.documentElement
  root.classList.add('dark')
  root.dataset.theme = theme.name

  Object.entries(theme.colors).forEach(([key, value]) => {
    root.style.setProperty(key, value)
  })
}

export function initTheme() {
  const theme = getTheme()
  applyTheme(theme)
  return theme
}
