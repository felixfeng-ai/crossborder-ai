export type ImageEditOperation =
  | 'inpaint'
  | 'outpaint'
  | 'remove_object'
  | 'upscale'

export interface ImageEditOperationOption {
  id: ImageEditOperation
  label: string
  description: string
  requiresMask: boolean
  requiresPrompt: boolean
}

export interface ImageEditDraft {
  operation: ImageEditOperation
  sourceAssetId: string
  maskAssetId: string
  prompt: string
  aspectRatio?: string
  scale?: number
  idempotencyKey?: string
}

export interface ImageEditRequest {
  source_asset_id: string
  operation: ImageEditOperation
  mask_asset_id: string | null
  prompt: string
  aspect_ratio: string
  scale: number
  idempotency_key?: string
}

export const IMAGE_EDIT_OPERATIONS: ImageEditOperationOption[] = [
  {
    id: 'inpaint',
    label: '局部重绘',
    description: '用蒙版圈定区域，按描述替换背景或商品局部',
    requiresMask: true,
    requiresPrompt: true,
  },
  {
    id: 'outpaint',
    label: '扩展画面',
    description: '向四周或目标比例扩展场景，保持光线与构图连续',
    requiresMask: false,
    requiresPrompt: true,
  },
  {
    id: 'remove_object',
    label: '消除物体',
    description: '移除蒙版中的杂物、水印或不需要的元素',
    requiresMask: true,
    requiresPrompt: false,
  },
  {
    id: 'upscale',
    label: '高清放大',
    description: '本地无损放大 2 倍或 4 倍，不依赖外部模型',
    requiresMask: false,
    requiresPrompt: false,
  },
]

const EDIT_CREDITS: Record<ImageEditOperation, number> = {
  inpaint: 6,
  outpaint: 6,
  remove_object: 5,
  upscale: 2,
}

export function imageEditCredits(
  operation: ImageEditOperation,
  count = 1,
): number {
  return EDIT_CREDITS[operation] * Math.max(1, Math.floor(count || 1))
}

export function validateImageEdit(
  draft: Pick<
    ImageEditDraft,
    'operation' | 'sourceAssetId' | 'maskAssetId' | 'prompt'
  >,
): string {
  const option = IMAGE_EDIT_OPERATIONS.find(
    (item) => item.id === draft.operation,
  )
  if (!option) return '请选择有效的编辑方式'
  if (!draft.sourceAssetId) return '请选择需要编辑的源图片'
  if (option.requiresMask && !draft.maskAssetId) {
    return '该编辑方式需要选择蒙版图'
  }
  if (option.requiresPrompt && !draft.prompt.trim()) {
    return '请输入本次编辑要求'
  }
  return ''
}

export function buildImageEditRequest(draft: ImageEditDraft): ImageEditRequest {
  return {
    source_asset_id: draft.sourceAssetId,
    operation: draft.operation,
    mask_asset_id: draft.maskAssetId || null,
    prompt: draft.prompt.trim(),
    aspect_ratio: draft.aspectRatio || '',
    scale: draft.operation === 'upscale' ? Math.max(2, draft.scale || 2) : 1,
    idempotency_key: draft.idempotencyKey,
  }
}
