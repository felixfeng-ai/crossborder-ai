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
      className="grid gap-2 sm:grid-cols-3"
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
              'flex min-h-[72px] items-start gap-3 rounded-lg border px-3.5 py-3 text-left transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
              active
                ? 'border-[color:var(--factory-accent)] bg-[color:var(--factory-accent)]/8'
                : 'border-border bg-background hover:bg-accent/50',
              disabled && 'cursor-not-allowed opacity-60',
            )}
          >
            <span
              className={cn(
                'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border',
                active
                  ? 'border-[color:var(--factory-accent)]/30 text-[var(--factory-accent)]'
                  : 'border-border text-muted-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium">{mode.label}</span>
              <span className="mt-1 block text-[11px] leading-5 text-muted-foreground">
                {mode.description}
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
