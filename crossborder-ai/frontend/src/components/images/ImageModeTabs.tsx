import { Box, Image, Sparkles } from 'lucide-react'

import {
  IMAGE_GENERATION_MODES,
  type ImageGenerationMode,
} from '@/lib/images/generation'
import { cn } from '@/utils/cn'


const MODE_ICONS = {
  product_scene: Box,
  free_creation: Sparkles,
  platform_white: Image,
} satisfies Record<ImageGenerationMode, typeof Box>


export function ImageModeTabs({
  value,
  onChange,
  disabled = false,
}: {
  value: ImageGenerationMode
  onChange: (mode: ImageGenerationMode) => void
  disabled?: boolean
}) {
  return (
    <div
      className="grid grid-cols-3 gap-1 rounded-md border border-border bg-background p-1"
      role="tablist"
      aria-label="图片生成模式"
    >
      {IMAGE_GENERATION_MODES.map((mode) => {
        const Icon = MODE_ICONS[mode.id]
        const active = value === mode.id
        return (
          <button
            key={mode.id}
            type="button"
            role="tab"
            aria-selected={active}
            disabled={disabled}
            onClick={() => onChange(mode.id)}
            className={cn(
              'flex min-h-[60px] flex-col items-start justify-center gap-1 rounded-[4px] border px-2.5 py-2 text-left transition-colors sm:flex-row sm:items-center sm:gap-2.5 sm:px-3 sm:py-2.5',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
              active
                ? 'border-[color:var(--factory-accent)]/55 bg-[color:var(--factory-accent)]/8'
                : 'border-transparent hover:bg-accent/45',
              disabled && 'cursor-not-allowed opacity-60',
            )}
          >
            <span
              className={cn(
                'flex h-7 w-7 shrink-0 items-center justify-center rounded-[4px] sm:h-8 sm:w-8',
                active
                  ? 'bg-[color:var(--factory-accent)]/12 text-[var(--factory-accent)]'
                  : 'bg-secondary/70 text-muted-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
            </span>
            <span className="min-w-0">
              <span className="block text-xs font-medium leading-5 sm:text-[13px]">{mode.label}</span>
              <span className="mt-0.5 hidden truncate text-[11px] leading-4 text-muted-foreground sm:block">
                {mode.description}
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
