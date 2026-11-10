import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/utils/cn'

const badgeVariants = cva(
  'inline-flex items-center whitespace-nowrap rounded border px-2 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary text-primary-foreground',
        secondary: 'border-border bg-secondary text-secondary-foreground',
        destructive: 'border-[color:rgba(217,139,112,0.3)] bg-[color:rgba(217,139,112,0.12)] text-[var(--factory-coral)]',
        outline: 'border-border bg-transparent text-foreground',
        success: 'border-[color:rgba(157,187,173,0.3)] bg-[color:rgba(157,187,173,0.12)] text-[var(--factory-mint)]',
        warning: 'border-[color:rgba(216,181,109,0.3)] bg-[color:rgba(216,181,109,0.12)] text-[var(--factory-accent)]',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
