import { Loader2 } from 'lucide-react'
import { BrandMark } from '@/components/brand/BrandMark'

export function RouteFallback({ fullScreen = false }: { fullScreen?: boolean }) {
  return (
    <div
      className={
        fullScreen
          ? 'flex min-h-[100dvh] items-center justify-center bg-[var(--factory-ground)]'
          : 'flex min-h-48 items-center justify-center'
      }
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-3 border border-border bg-[var(--factory-panel)] px-4 py-3 text-sm text-muted-foreground">
        <BrandMark className="h-5 w-5 text-foreground" />
        <span>正在载入工作区</span>
        <Loader2 className="h-4 w-4 animate-spin text-[var(--factory-accent)]" />
      </div>
    </div>
  )
}
