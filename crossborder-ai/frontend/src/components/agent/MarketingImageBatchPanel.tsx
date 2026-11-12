import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Images, Loader2, Sparkles, X } from 'lucide-react'
import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  BATCH_OUTPUT_OPTIONS,
  MARKETING_IMAGE_DIRECTIONS,
  buildMarketingImagePrompt,
  estimatedMarketingImageCredits,
  type MarketingImageDirection,
} from '@/lib/agent/campaignAssets'
import { toErrorMessage } from '@/utils/errorMessage'

interface MarketingImageBatchPanelProps {
  campaignId: string
  onCreated: () => void
  onClose: () => void
}

export function MarketingImageBatchPanel({
  campaignId,
  onCreated,
  onClose,
}: MarketingImageBatchPanelProps) {
  const [count, setCount] = useState<(typeof BATCH_OUTPUT_OPTIONS)[number]>(2)
  const [direction, setDirection] = useState<MarketingImageDirection>('product_hero')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  const createMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post(
        '/images/generate',
        {
          campaign_id: campaignId,
          prompt: buildMarketingImagePrompt(direction, note),
          num_outputs: count,
        },
        {
          headers: { 'Idempotency-Key': crypto.randomUUID() },
        },
      )
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: () => {
      onCreated()
      onClose()
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '营销图片批量生成失败'))
    },
  })

  return (
    <div className="mt-2 border border-border bg-background p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-medium">
            <Sparkles className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
            批量生成营销图片
          </p>
          <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
            每张图片独立入库，完成后可在活动素材板中管理和转视频。
          </p>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="h-8 w-8 shrink-0"
          aria-label="关闭批量生成"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-[180px_minmax(0,1fr)]">
        <div className="space-y-1.5">
          <Label htmlFor="marketing-image-direction">图片方向</Label>
          <select
            id="marketing-image-direction"
            value={direction}
            onChange={(event) => setDirection(event.target.value as MarketingImageDirection)}
            className="h-9 w-full border border-input bg-background px-2.5 text-xs outline-none focus:ring-2 focus:ring-ring"
          >
            {MARKETING_IMAGE_DIRECTIONS.map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <Label>生成数量</Label>
          <div className="grid grid-cols-3 border border-border p-0.5">
            {BATCH_OUTPUT_OPTIONS.map((value) => (
              <Button
                key={value}
                type="button"
                variant={count === value ? 'secondary' : 'ghost'}
                size="sm"
                className="h-8 text-xs"
                aria-pressed={count === value}
                onClick={() => setCount(value)}
              >
                {value} 张
              </Button>
            ))}
          </div>
        </div>

        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="marketing-image-note">补充要求</Label>
          <Input
            id="marketing-image-note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="例如：暖光、圣诞氛围、9:16 构图，商品 Logo 必须清晰"
            className="h-9 text-xs"
            maxLength={500}
          />
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Images className="h-3.5 w-3.5" />
          预计 {estimatedMarketingImageCredits(count)} 积分
        </div>
        <div className="flex items-center gap-2">
          {error && <span className="text-[11px] text-destructive">{error}</span>}
          <Button
            type="button"
            size="sm"
            disabled={createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            )}
            {createMutation.isPending ? '提交中...' : `生成 ${count} 张`}
          </Button>
        </div>
      </div>
    </div>
  )
}
