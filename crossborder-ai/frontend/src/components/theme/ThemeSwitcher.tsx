import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, Monitor, Moon, Sun, Waves } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useThemeStore } from '@/stores/themeStore'
import { THEME_OPTIONS, type ThemeMode } from '@/utils/themes'
import { cn } from '@/utils/cn'

const THEME_ICONS = {
  graphite: Moon,
  paper: Sun,
  harbor: Waves,
  system: Monitor,
} satisfies Record<ThemeMode, typeof Moon>

export function ThemeSwitcher({
  compact = false,
  className,
}: {
  compact?: boolean
  className?: string
}) {
  const { mode, setMode } = useThemeStore()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const current = THEME_OPTIONS.find((theme) => theme.value === mode) || THEME_OPTIONS[0]
  const CurrentIcon = THEME_ICONS[current.value]

  useEffect(() => {
    if (!open) return
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      <Button
        variant="ghost"
        size="sm"
        className={cn('gap-1.5 px-2 text-muted-foreground', className)}
        aria-label="切换主题"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <CurrentIcon className="h-4 w-4" />
        {!compact && (
          <span className="hidden text-xs md:inline-block">{current.label}</span>
        )}
        {!compact && <ChevronDown className="hidden h-3 w-3 md:block" />}
      </Button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-[calc(100%+6px)] z-[70] w-64 border border-border bg-[var(--factory-panel)] p-1 shadow-xl"
        >
          <div className="px-2 py-1.5 text-xs text-muted-foreground">界面主题</div>
          <div className="mb-1 border-t border-border" />
        {THEME_OPTIONS.map((theme) => {
          const Icon = THEME_ICONS[theme.value]
          return (
            <button
              type="button"
              key={theme.value}
              role="menuitemradio"
              aria-checked={mode === theme.value}
              className="flex w-full gap-3 rounded px-2 py-2.5 text-left hover:bg-accent"
              onClick={() => {
                setMode(theme.value)
                setOpen(false)
              }}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{theme.label}</span>
                  {mode === theme.value && <Check className="h-3.5 w-3.5" />}
                </span>
                <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                  {theme.description}
                </span>
                <span className="mt-2 flex gap-1">
                  {theme.swatches.map((color) => (
                    <span
                      key={color}
                      className="h-2.5 w-5 border border-black/10"
                      style={{ backgroundColor: color }}
                    />
                  ))}
                </span>
              </span>
            </button>
          )
        })}
        </div>
      )}
    </div>
  )
}
