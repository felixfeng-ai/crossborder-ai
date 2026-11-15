import { useMemo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Eraser,
  Loader2,
  Maximize2,
  Paintbrush,
  Sparkles,
  ZoomIn,
} from 'lucide-react'

import apiClient from '@/api/client'
import { ReferenceImagePicker } from '@/components/images/ReferenceImagePicker'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { waitForImageTask, type ImageTaskStatus } from '@/lib/images/taskPolling'
import {
  IMAGE_EDIT_OPERATIONS,
  buildImageEditRequest,
  imageEditCredits,
  validateImageEdit,
  type ImageEditOperation,
} from '@/lib/images/editing'
import type { WorkbenchAsset } from '@/lib/images/workbench'
import { toErrorMessage } from '@/utils/errorMessage'
import { cn } from '@/utils/cn'


const OPERATION_ICONS = {
  inpaint: Paintbrush,
  outpaint: Maximize2,
  remove_object: Eraser,
  upscale: ZoomIn,
} satisfies Record<ImageEditOperation, typeof Paintbrush>


export function ImageEditingPanel({
  assets,
  onUpload,
  onCompleted,
}: {
  assets: WorkbenchAsset[]
  onUpload: () => void
  onCompleted: () => void
}) {
  const [operation, setOperation] = useState<ImageEditOperation>('inpaint')
  const [sourceIds, setSourceIds] = useState<string[]>([])
  const [maskIds, setMaskIds] = useState<string[]>([])
  const [prompt, setPrompt] = useState('')
  const [aspectRatio, setAspectRatio] = useState('')
  const [scale, setScale] = useState<2 | 4>(2)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const option = useMemo(
    () => IMAGE_EDIT_OPERATIONS.find((item) => item.id === operation)!,
    [operation],
  )
  const sourceAssetId = sourceIds[0] || ''
  const maskAssetId = maskIds[0] || ''
  const validationError = validateImageEdit({
    operation,
    sourceAssetId,
    maskAssetId,
    prompt,
  })
  const credits = imageEditCredits(operation)

  const editMutation = useMutation({
    mutationFn: async () => {
      if (validationError) throw new Error(validationError)
      const request = buildImageEditRequest({
        operation,
        sourceAssetId,
        maskAssetId,
        prompt,
        aspectRatio,
        scale,
        idempotencyKey: crypto.randomUUID(),
      })
      const response = await apiClient.post('/images/edit', request)
      return waitForImageTask(
        response.data.task_id,
        async (taskId): Promise<ImageTaskStatus> => {
          const status = await apiClient.get(`/images/status/${taskId}`)
          return status.data
        },
      )
    },
    onMutate: () => {
      setError('')
      setSuccess('')
    },
    onSuccess: (task) => {
      setSuccess(`图片编辑完成，共生成 ${task.image_urls.length} 张结果`)
      onCompleted()
    },
    onError: (mutationError) => {
      setError(toErrorMessage(mutationError, '图片编辑失败'))
    },
  })

  return (
    <section className="border-y border-border bg-[var(--factory-panel)] py-5 pb-24 lg:pb-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="section-title">图片编辑</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            局部重绘、扩展画面、消除物体或本地放大，结果自动进入素材库。
          </p>
        </div>
        <span className="metric-number text-xs text-muted-foreground">
          预计 {credits} 积分
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {IMAGE_EDIT_OPERATIONS.map((item) => {
          const Icon = OPERATION_ICONS[item.id]
          const active = item.id === operation
          return (
            <button
              key={item.id}
              type="button"
              aria-pressed={active}
              disabled={editMutation.isPending}
              onClick={() => {
                setOperation(item.id)
                setError('')
                setSuccess('')
              }}
              className={cn(
                'flex min-h-[68px] items-start gap-2.5 border px-3 py-2.5 text-left transition-colors',
                active
                  ? 'border-[color:var(--factory-accent)] bg-[color:var(--factory-accent)]/8'
                  : 'border-border bg-background hover:bg-accent/50',
              )}
            >
              <span className="mt-0.5 text-[var(--factory-accent)]">
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-xs font-medium">{item.label}</span>
                <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                  {item.description}
                </span>
              </span>
            </button>
          )
        })}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          <ReferenceImagePicker
            assets={assets}
            selectedIds={sourceIds}
            onChange={(ids) => setSourceIds(ids.slice(-1))}
            onUpload={onUpload}
            max={1}
            disabled={editMutation.isPending}
            label="源图片"
            description="选择需要重绘、扩图、消除或放大的商品素材"
          />
          {option.requiresMask && (
            <ReferenceImagePicker
              assets={assets}
              selectedIds={maskIds}
              onChange={(ids) => setMaskIds(ids.slice(-1))}
              onUpload={onUpload}
              max={1}
              disabled={editMutation.isPending}
              label="蒙版图"
              description="白色区域会被编辑，黑色区域保持不变"
            />
          )}
        </div>

        <div className="space-y-3">
          {option.requiresPrompt && (
            <label className="block space-y-1.5 text-xs">
              <span className="font-medium">编辑要求</span>
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                rows={4}
                maxLength={2000}
                disabled={editMutation.isPending}
                placeholder={
                  operation === 'outpaint'
                    ? '例如：向右侧扩展成 16:9 场景，延续木桌与暖光'
                    : '例如：把背景替换成米白色摄影棚，保持包装文字和 Logo 不变'
                }
                className="w-full resize-y rounded-md border border-input bg-background px-3 py-2.5 text-xs leading-5 outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
              />
            </label>
          )}
          {operation === 'outpaint' && (
            <label className="block space-y-1.5 text-xs">
              <span className="font-medium">目标比例</span>
              <select
                value={aspectRatio}
                onChange={(event) => setAspectRatio(event.target.value)}
                disabled={editMutation.isPending}
                className="h-9 w-full border border-input bg-background px-2.5 text-xs outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">跟随源图</option>
                <option value="1:1">1:1</option>
                <option value="4:5">4:5</option>
                <option value="16:9">16:9</option>
                <option value="9:16">9:16</option>
              </select>
            </label>
          )}
          {operation === 'upscale' && (
            <div>
              <p className="text-xs font-medium">放大倍率</p>
              <div className="mt-2 grid grid-cols-2 border border-border p-0.5">
                {[2, 4].map((value) => (
                  <Button
                    key={value}
                    type="button"
                    size="sm"
                    variant={scale === value ? 'secondary' : 'ghost'}
                    className="h-8 text-xs"
                    aria-pressed={scale === value}
                    onClick={() => setScale(value as 2 | 4)}
                  >
                    {value}x
                  </Button>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between gap-3 border-t border-border pt-3 pr-20 lg:pr-0">
            <div>
              <p className="metric-number text-sm font-medium">{credits} 积分</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {operation === 'upscale' ? '本地处理，成功后扣费' : '成功后扣费'}
              </p>
            </div>
            <Button
              disabled={Boolean(validationError) || editMutation.isPending}
              onClick={() => editMutation.mutate()}
            >
              {editMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-2 h-4 w-4" />
              )}
              {editMutation.isPending ? '处理中...' : '开始编辑'}
            </Button>
          </div>
          {validationError && !editMutation.isPending && (
            <p className="text-[11px] text-muted-foreground">{validationError}</p>
          )}
        </div>
      </div>

      {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
      {success && (
        <p role="status" className="mt-3 text-xs text-[var(--factory-success)]">
          {success}
        </p>
      )}
    </section>
  )
}
