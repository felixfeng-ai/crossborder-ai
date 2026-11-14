import type { ReactNode } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'

import { cn } from '@/utils/cn'

export function formatNumber(value: number, digits = 0): string {
  return new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value)
}

export function formatMoney(value: number): string {
  return `¥${formatNumber(value, 2)}`
}

export function AdminPageHeader({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-[24px] font-semibold leading-tight text-foreground">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  )
}

export function AdminPanel({
  title,
  description,
  action,
  children,
  className,
}: {
  title?: string
  description?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn('border border-border bg-[var(--factory-panel)]', className)}>
      {(title || action) && (
        <div className="flex min-h-14 items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold text-foreground">{title}</h2>}
            {description && (
              <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
            )}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function AdminLoading({ label = '正在载入运营数据' }: { label?: string }) {
  return (
    <div className="flex min-h-44 items-center justify-center" role="status">
      <Loader2 className="mr-2 h-4 w-4 animate-spin text-[var(--factory-accent)]" />
      <span className="text-sm text-muted-foreground">{label}</span>
    </div>
  )
}

export function AdminError({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      className="flex min-h-44 flex-col items-center justify-center gap-3 text-center"
      role="alert"
    >
      <AlertTriangle className="h-5 w-5 text-[var(--factory-coral)]" />
      <div>
        <p className="text-sm font-medium text-foreground">运营数据加载失败</p>
        <p className="mt-1 text-xs text-muted-foreground">保留当前页面，可重新请求。</p>
      </div>
      <button
        type="button"
        className="text-sm text-[var(--factory-accent)] underline-offset-4 hover:underline"
        onClick={onRetry}
      >
        重新加载
      </button>
    </div>
  )
}

export function AdminStatusPill({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'good' | 'warning' | 'danger'
  children: ReactNode
}) {
  const tones = {
    neutral: 'border-border bg-secondary text-muted-foreground',
    good: 'border-[color-mix(in_srgb,var(--factory-mint)_35%,transparent)] bg-[color-mix(in_srgb,var(--factory-mint)_12%,transparent)] text-[var(--factory-mint)]',
    warning: 'border-[color-mix(in_srgb,var(--factory-accent)_35%,transparent)] bg-[color-mix(in_srgb,var(--factory-accent)_10%,transparent)] text-[var(--factory-accent)]',
    danger: 'border-[color-mix(in_srgb,var(--factory-coral)_35%,transparent)] bg-[color-mix(in_srgb,var(--factory-coral)_10%,transparent)] text-[var(--factory-coral)]',
  }
  return (
    <span
      className={cn(
        'inline-flex h-5 items-center whitespace-nowrap rounded-[4px] border px-1.5 text-[11px] font-medium',
        tones[tone],
      )}
    >
      {children}
    </span>
  )
}
