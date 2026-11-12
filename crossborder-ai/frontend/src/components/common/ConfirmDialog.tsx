import { useEffect } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'


interface ConfirmDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  pending?: boolean
  destructive?: boolean
  onCancel: () => void
  onConfirm: () => void
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '确认删除',
  pending = false,
  destructive = true,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) onCancel()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onCancel, open, pending])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/65 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pending) onCancel()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
        className="w-full max-w-md border border-border bg-[var(--factory-panel)] p-5 shadow-2xl"
      >
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center border border-destructive/30 bg-destructive/10">
            <AlertTriangle className="h-4 w-4 text-destructive" />
          </span>
          <div className="min-w-0">
            <h2 id="confirm-dialog-title" className="text-base font-semibold">
              {title}
            </h2>
            <p
              id="confirm-dialog-description"
              className="mt-2 text-sm leading-6 text-muted-foreground"
            >
              {description}
            </p>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            autoFocus
            disabled={pending}
            onClick={onCancel}
          >
            取消
          </Button>
          <Button
            variant={destructive ? 'destructive' : 'default'}
            size="sm"
            disabled={pending}
            onClick={onConfirm}
          >
            {pending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
            {pending ? '处理中...' : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
