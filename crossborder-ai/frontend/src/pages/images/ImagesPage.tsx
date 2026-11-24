/** 图片工作台：统一处理上传、平台白底、AI 生成、编辑和历史素材复用。 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useSearchParams } from 'react-router-dom'
import {
  Check,
  Copy,
  Download,
  Grid3X3,
  ImagePlus,
  Images,
  Loader2,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import ConfirmDialog from '@/components/common/ConfirmDialog'
import { ImageModeTabs } from '@/components/images/ImageModeTabs'
import { ImageEditingPanel } from '@/components/images/ImageEditingPanel'
import { ReferenceImagePicker } from '@/components/images/ReferenceImagePicker'
import apiClient from '@/api/client'
import { waitForImageTask, type ImageTaskStatus } from '@/lib/images/taskPolling'
import {
  buildLibraryItems,
  formatFileSize,
  type GeneratedImageHistory,
  type WorkbenchAsset,
  type WorkbenchLibraryItem,
} from '@/lib/images/workbench'
import { toErrorMessage } from '@/utils/errorMessage'
import { resolveMediaUrl } from '@/lib/apiUrl'
import {
  imageUploadErrorMessage,
  uploadImageFile,
  validateImageUpload,
} from '@/lib/images/upload'
import { useAgentPageContext } from '@/lib/agent/useAgentPageContext'
import {
  IMAGE_ASPECT_RATIOS,
  IMAGE_GENERATION_MODES,
  IMAGE_QUALITY_TIERS,
  buildImageGenerationRequest,
  effectiveImageGenerationMode,
  imageGenerationCredits,
  validateImageGeneration,
  type ImageGenerationMode,
  type ImageGenerationProvider,
  type ImageQualityTier,
} from '@/lib/images/generation'
import { imagePromptFromProductTitle } from '@/lib/products/imageWorkbenchContext'

interface PlatformPreset {
  id: string
  platform: string
  label: string
  width: number
  height: number
  note: string
}

interface ImageProviderCapability {
  provider: ImageGenerationProvider
  configured: boolean
  modes: string[]
  reference_images: boolean
}

interface ImageCapabilities {
  providers: ImageProviderCapability[]
}

type LibraryFilter = 'all' | 'upload' | 'processed' | 'generated'
type GenerationState = 'idle' | 'submitting' | 'generating' | 'completed' | 'failed'
type ImageGenerationResult =
  | { kind: 'processed'; asset: WorkbenchAsset }
  | { kind: 'generated'; task: ImageTaskStatus }

const IMAGE_STYLE_PRESETS = [
  { id: '', label: '跟随提示词', prompt: null },
  { id: 'clean_studio', label: '干净棚拍', prompt: 'clean commercial studio lighting' },
  { id: 'warm_lifestyle', label: '暖调生活', prompt: 'warm lifestyle photography, natural window light' },
  { id: 'editorial', label: '编辑大片', prompt: 'editorial campaign photography, refined art direction' },
  {
    id: 'realistic_photo',
    label: '真人摄影',
    prompt:
      'photorealistic editorial photography, natural skin texture, realistic facial proportions, true-to-life anatomy, soft daylight, 50mm lens, shallow depth of field, no beautification, no illustration',
  },
  { id: 'festive', label: '节日氛围', prompt: 'subtle festive atmosphere, premium seasonal styling' },
] as const

export default function ImagesPage() {
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedId, setSelectedId] = useState('')
  const [presetId, setPresetId] = useState('amazon-main')
  const [filter, setFilter] = useState<LibraryFilter>('all')
  const [copied, setCopied] = useState(false)
  const [mode, setMode] = useState<ImageGenerationMode>('product_scene')
  const [qualityTier, setQualityTier] = useState<ImageQualityTier>('standard')
  const [aspectRatio, setAspectRatio] = useState('1:1')
  const [numOutputs, setNumOutputs] = useState(1)
  const [referenceAssetIds, setReferenceAssetIds] = useState<string[]>([])
  const [negativePrompt, setNegativePrompt] = useState('')
  const [stylePreset, setStylePreset] = useState('')
  const [provider, setProvider] = useState<ImageGenerationProvider>('auto')
  const [useBrandPersona, setUseBrandPersona] = useState(true)
  const [generationState, setGenerationState] = useState<GenerationState>('idle')
  const [prompt, setPrompt] = useState(() =>
    imagePromptFromProductTitle(searchParams.get('title')),
  )
  const [actionError, setActionError] = useState('')
  const [actionSuccess, setActionSuccess] = useState('')
  const [uploadProgress, setUploadProgress] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<WorkbenchLibraryItem | null>(null)

  // 素材、平台预设、生成历史和服务能力并行加载，页面先展示可用部分。
  const assetsQuery = useQuery<WorkbenchAsset[]>({
    queryKey: ['image-assets'],
    queryFn: async () => {
      const response = await apiClient.get('/images/assets')
      return response.data.items || []
    },
  })

  const presetsQuery = useQuery<PlatformPreset[]>({
    queryKey: ['image-platform-presets'],
    queryFn: async () => {
      const response = await apiClient.get('/images/presets')
      return response.data.items || []
    },
  })

  const historyQuery = useQuery<GeneratedImageHistory[]>({
    queryKey: ['image-generation-history'],
    queryFn: async () => {
      const response = await apiClient.get('/images/history')
      return response.data || []
    },
  })

  const capabilitiesQuery = useQuery<ImageCapabilities>({
    queryKey: ['image-capabilities'],
    queryFn: async () => {
      const response = await apiClient.get('/images/capabilities')
      return response.data
    },
  })

  const items = useMemo(
    () => buildLibraryItems(assetsQuery.data || [], historyQuery.data || []),
    [assetsQuery.data, historyQuery.data],
  )

  const visibleItems = useMemo(
    () => (filter === 'all' ? items : items.filter((item) => item.kind === filter)),
    [filter, items],
  )

  useEffect(() => {
    if (!items.length) {
      if (selectedId) setSelectedId('')
      return
    }
    if (!items.some((item) => item.id === selectedId)) {
      // 默认优先进入可编辑的本地素材，AI 生成历史仍保留在素材库中。
      setSelectedId(items.find((item) => item.kind !== 'generated')?.id || items[0].id)
    }
  }, [items, selectedId])

  const selected = items.find((item) => item.id === selectedId) || null
  const selectedAsset = (assetsQuery.data || []).find((asset) => asset.id === selectedId) || null
  const selectedPreset = (presetsQuery.data || []).find((preset) => preset.id === presetId) || null
  const localAssets = (assetsQuery.data || []).filter(
    (asset) => asset.kind !== 'processed' || asset.source_asset_id,
  )
  const selectedMode = IMAGE_GENERATION_MODES.find((item) => item.id === mode)
  const billingMode = effectiveImageGenerationMode(
    mode,
    mode === 'product_scene' || mode === 'platform_white'
      ? referenceAssetIds.length
      : undefined,
  )
  const estimatedCredits = imageGenerationCredits(
    mode,
    qualityTier,
    numOutputs,
    mode === 'product_scene' ? referenceAssetIds.length : undefined,
  )
  const validationError = validateImageGeneration({
    mode,
    prompt,
    referenceAssetIds,
    qualityTier,
  })
  const generationPending =
    generationState === 'submitting' || generationState === 'generating'

  // 全局 Agent 需要知道当前图片和平台上下文，才能回答“处理这张图”之类的指令。
  useAgentPageContext({
    route: '/app/images',
    page: '图片工作台',
    details: [
      selected ? `当前素材：${selected.name}` : '尚未选择素材',
      selectedPreset ? `平台预设：${selectedPreset.label}` : '',
    ].filter(Boolean),
    asset_id: selected?.assetId || selected?.id,
    asset_name: selected?.name,
  })

  // 上传成功后自动把新素材加入当前生成参考图，减少一次重复选择。
  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      return uploadImageFile<WorkbenchAsset>(file, {
        onProgress: setUploadProgress,
      })
    },
    onMutate: () => {
      setActionError('')
      setActionSuccess('')
      setUploadProgress(0)
    },
    onSuccess: (asset) => {
      setUploadProgress(100)
      setActionSuccess(
        `图片上传成功：${asset.name} · ${asset.width} × ${asset.height}`,
      )
      queryClient.invalidateQueries({ queryKey: ['image-assets'] })
      setSelectedId(asset.id)
      if (mode !== 'free_creation' && referenceAssetIds.length < 4) {
        setReferenceAssetIds((current) => (
          current.includes(asset.id) ? current : [...current, asset.id]
        ))
      }
    },
    onError: (error) => {
      setUploadProgress(0)
      setActionError(imageUploadErrorMessage(error))
    },
  })

  // 生成历史与本地素材的删除接口不同，必须按 item 来源选择真实资源。
  const deleteMutation = useMutation({
    mutationFn: async (item: WorkbenchLibraryItem) => {
      if (item.taskId && !item.assetId) {
        await apiClient.delete(`/images/history/${item.taskId}`)
        return
      }
      await apiClient.delete(`/images/assets/${item.id}`)
    },
    onSuccess: () => {
      setSelectedId('')
      setDeleteTarget(null)
      queryClient.invalidateQueries({ queryKey: ['image-assets'] })
      queryClient.invalidateQueries({ queryKey: ['image-generation-history'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '删除失败')),
  })

  // 生成任务先提交并拿到 task_id，再轮询终态，不能把“已提交”误报为完成。
  const generateMutation = useMutation({
    mutationFn: async () => {
      const error = validateImageGeneration({
        mode,
        prompt,
        referenceAssetIds,
        qualityTier,
      })
      if (error) throw new Error(error)

      if (mode === 'platform_white') {
        const sourceAssetId = referenceAssetIds[0]
        if (!sourceAssetId) throw new Error('请先选择一张商品图')
        const response = await apiClient.post<WorkbenchAsset>(
          `/images/assets/${sourceAssetId}/process`,
          { preset_id: presetId },
        )
        return {
          kind: 'processed',
          asset: response.data,
        } satisfies ImageGenerationResult
      }

      const style = IMAGE_STYLE_PRESETS.find((item) => item.id === stylePreset)
      const styledPrompt = style?.prompt
        ? `${prompt.trim()}，${style.prompt}`
        : prompt
      const request = buildImageGenerationRequest({
        mode,
        prompt: styledPrompt,
        referenceAssetIds,
        qualityTier,
        aspectRatio,
        platformPresetId: null,
        negativePrompt,
        stylePreset: stylePreset || null,
        useBrandPersona,
        provider,
        numOutputs,
        idempotencyKey: crypto.randomUUID(),
      })
      const response = await apiClient.post('/images/generate', request)
      setGenerationState('generating')
      const task = await waitForImageTask(
        response.data.task_id,
        async (taskId): Promise<ImageTaskStatus> => {
          const status = await apiClient.get(`/images/status/${taskId}`)
          return status.data
        },
      )
      return { kind: 'generated', task } satisfies ImageGenerationResult
    },
    onMutate: () => {
      setActionError('')
      setActionSuccess('')
      setGenerationState('submitting')
    },
    onSuccess: (result) => {
      setGenerationState('completed')
      queryClient.invalidateQueries({ queryKey: ['image-generation-history'] })
      queryClient.invalidateQueries({ queryKey: ['image-assets'] })
      if (result.kind === 'processed') {
        setSelectedId(result.asset.id)
        setFilter('processed')
        setActionSuccess(`平台白底图已生成：${result.asset.name}`)
      } else {
        setActionSuccess(
          `图片生成完成，共 ${result.task.image_urls.length} 张，已同步到素材库`,
        )
      }
    },
    onError: (error) => {
      setGenerationState('failed')
      setActionError(toErrorMessage(error, '图片生成失败'))
    },
  })

  const chooseFile = (files?: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    const validationError = validateImageUpload(file)
    if (validationError) {
      setActionError(validationError)
      return
    }
    setActionError('')
    setActionSuccess('')
    uploadMutation.mutate(file)
  }

  const copySelectedUrl = async () => {
    if (!selected) return
    const url = selected.image_url.startsWith('http')
      ? selected.image_url
      : resolveMediaUrl(selected.image_url)
    await navigator.clipboard.writeText(url)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  const changeMode = (nextMode: ImageGenerationMode) => {
    setMode(nextMode)
    setGenerationState('idle')
    if (nextMode === 'free_creation') {
      setUseBrandPersona(false)
    } else {
      setUseBrandPersona(true)
    }
    if (
      nextMode === 'product_scene' &&
      provider === 'aliyun' &&
      referenceAssetIds.length > 0
    ) {
      setProvider('auto')
    }
    if (
      nextMode !== 'free_creation' &&
      referenceAssetIds.length === 0 &&
      selectedAsset
    ) {
      setReferenceAssetIds([selectedAsset.id])
    }
  }

  const providerCapabilities = capabilitiesQuery.data?.providers || []
  const availableProviderNames = new Set(
    providerCapabilities.filter((item) => item.configured).map((item) => item.provider),
  )

  const filterItems: Array<{ id: LibraryFilter; label: string; count: number }> = [
    { id: 'all', label: '全部', count: items.length },
    { id: 'upload', label: '上传', count: items.filter((item) => item.kind === 'upload').length },
    { id: 'processed', label: '白底图', count: items.filter((item) => item.kind === 'processed').length },
    { id: 'generated', label: 'AI 生成', count: items.filter((item) => item.kind === 'generated').length },
  ]

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="mx-auto w-full max-w-[1480px] space-y-7"
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={(event) => {
          chooseFile(event.target.files)
          event.target.value = ''
        }}
      />

      <div className="flex flex-wrap items-start justify-between gap-5">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Images className="h-5 w-5 text-primary" />
            商品图片工作台
          </h1>
          <p className="mt-1.5 max-w-2xl text-[13px] leading-6 text-muted-foreground">
            从商品参考图生成场景图，或创作投放视觉、处理平台白底素材。
          </p>
        </div>
        <Button
          variant="outline"
          className="h-9"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadMutation.isPending}
        >
          {uploadMutation.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Upload className="mr-2 h-4 w-4" />
          )}
          {uploadMutation.isPending
            ? uploadProgress >= 100
              ? '图片优化中...'
              : `上传中 ${uploadProgress}%`
            : '上传图片'}
        </Button>
      </div>

      <section className="rounded-lg border border-border bg-[var(--factory-panel)] p-5 sm:p-6 lg:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="section-title">生成方案</h2>
            <p className="mt-1.5 max-w-2xl text-xs leading-5 text-muted-foreground">
              {selectedMode?.description}
            </p>
          </div>
          <span className="rounded-[4px] border border-border bg-background px-2.5 py-1.5 text-xs text-muted-foreground">
            {selectedMode?.label}
            <span className="mx-1.5 text-border">/</span>
            {IMAGE_QUALITY_TIERS[qualityTier].label}
            <span className="mx-1.5 text-border">/</span>
            <span className="metric-number">{numOutputs} 张</span>
          </span>
        </div>

        <div className="mt-5">
          <ImageModeTabs
            value={mode}
            onChange={changeMode}
            disabled={generationPending}
          />
        </div>

        <div className="mt-5 grid overflow-hidden rounded-md border border-border bg-background/35 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-5 p-4 sm:p-5">
            {mode !== 'platform_white' ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <label htmlFor="image-prompt" className="text-[13px] font-medium leading-5">
                    画面描述
                  </label>
                  <span className="metric-number text-xs text-muted-foreground">
                    {prompt.length}/2000
                  </span>
                </div>
                <textarea
                  id="image-prompt"
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder={
                    mode === 'product_scene'
                      ? '例如：保持商品完全一致，放在冬季暖光客厅，木质桌面，浅景深，商业摄影'
                      : '例如：黑白电影感几何海报，只保留商品轮廓和一处暖金色反光'
                  }
                  rows={5}
                  maxLength={2000}
                  disabled={generationPending}
                  className="min-h-[168px] w-full resize-y rounded-md border border-input bg-background px-3.5 py-3 text-[14px] leading-6 outline-none transition-colors placeholder:text-muted-foreground focus:border-[color:var(--factory-accent)] focus:ring-2 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-60"
                />
                <div className="text-xs leading-5 text-muted-foreground">
                  <span>
                    {mode === 'product_scene'
                      ? referenceAssetIds.length > 0
                        ? '商品主体、Logo、材质和颜色会以参考图为准'
                        : '未选择参考图，将按文字生成，商品外观一致性会降低'
                      : '自由创作默认不注入品牌人设，需要时可手动开启'}
                  </span>
                </div>
              </div>
            ) : (
              <div className="rounded-md border border-border bg-background px-3.5 py-3.5">
                <p className="text-[13px] font-medium leading-5">本地白底适配</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  等比缩放并居中，透明区域填充纯白，不裁切或拉伸商品主体。
                  选择右上方平台尺寸后直接生成。
                </p>
                {selectedPreset && (
                  <p className="metric-number mt-2 text-xs">
                    {selectedPreset.platform} · {selectedPreset.width} × {selectedPreset.height}
                  </p>
                )}
              </div>
            )}

            {mode !== 'free_creation' && (
              <ReferenceImagePicker
                assets={localAssets}
                selectedIds={referenceAssetIds}
                onChange={setReferenceAssetIds}
                onUpload={() => fileInputRef.current?.click()}
                max={4}
                disabled={generationPending}
                description={
                  mode === 'product_scene'
                    ? referenceAssetIds.length > 0
                      ? '已选参考图会用于保持商品主体和关键细节一致'
                      : '参考图可选；不选时将仅根据画面描述生成，商品一致性会降低'
                    : '平台白底必须选择 1 张商品图'
                }
              />
            )}
          </div>

          <div className="space-y-5 border-t border-border p-4 sm:p-5 xl:border-l xl:border-t-0">
            <div>
              <p className="text-[13px] font-medium leading-5">输出质量</p>
              <div className="mt-2 grid grid-cols-3 border border-border p-0.5">
                {Object.values(IMAGE_QUALITY_TIERS).map((quality) => (
                  <button
                    key={quality.id}
                    type="button"
                    className={`h-9 px-2 text-[13px] transition-colors ${
                      qualityTier === quality.id
                        ? 'bg-secondary font-medium text-foreground'
                        : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'
                    }`}
                    aria-pressed={qualityTier === quality.id}
                    disabled={generationPending || mode === 'platform_white'}
                    onClick={() => setQualityTier(quality.id)}
                  >
                    {quality.label}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {IMAGE_QUALITY_TIERS[qualityTier].description}
              </p>
            </div>

            {mode !== 'platform_white' && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <label className="space-y-1.5 text-[13px] leading-5">
                    <span className="font-medium">画面比例</span>
                    <select
                      value={aspectRatio}
                      onChange={(event) => setAspectRatio(event.target.value)}
                      disabled={generationPending}
                      className="h-10 w-full border border-input bg-background px-2.5 text-[13px] outline-none focus:ring-2 focus:ring-ring"
                    >
                      {IMAGE_ASPECT_RATIOS.map((ratio) => (
                        <option key={ratio} value={ratio}>{ratio}</option>
                      ))}
                    </select>
                  </label>
                  <label className="space-y-1.5 text-[13px] leading-5">
                    <span className="font-medium">生成数量</span>
                    <select
                      value={numOutputs}
                      onChange={(event) => setNumOutputs(Number(event.target.value))}
                      disabled={generationPending}
                      className="h-10 w-full border border-input bg-background px-2.5 text-[13px] outline-none focus:ring-2 focus:ring-ring"
                    >
                      {[1, 2, 3, 4].map((count) => (
                        <option key={count} value={count}>{count} 张</option>
                      ))}
                    </select>
                  </label>
                </div>

                <details className="border-t border-border pt-4">
                  <summary className="cursor-pointer text-[13px] font-medium leading-5">
                    高级设置
                  </summary>
                  <div className="mt-4 space-y-4">
                    <label className="block space-y-1.5 text-[13px] leading-5">
                      <span className="text-muted-foreground">图片 Provider</span>
                      <select
                        value={provider}
                        onChange={(event) => setProvider(
                          event.target.value as ImageGenerationProvider,
                        )}
                        disabled={generationPending}
                        className="h-10 w-full border border-input bg-background px-2.5 text-[13px] outline-none focus:ring-2 focus:ring-ring"
                      >
                        <option value="auto">自动选择可用服务</option>
                        <option
                          value="seedream"
                          disabled={
                            (providerCapabilities.length > 0 &&
                              !availableProviderNames.has('seedream'))
                          }
                        >
                          Seedream 直连（火山方舟）
                        </option>
                        <option
                          value="replicate"
                          disabled={
                            providerCapabilities.length > 0 &&
                            !availableProviderNames.has('replicate')
                          }
                        >
                          Replicate Seedream
                        </option>
                        <option
                          value="aliyun"
                          disabled={
                            (mode === 'product_scene' &&
                              referenceAssetIds.length > 0) ||
                            (providerCapabilities.length > 0 &&
                              !availableProviderNames.has('aliyun'))
                          }
                        >
                          阿里云通义万相
                        </option>
                      </select>
                    </label>
                    <label className="block space-y-1.5 text-[13px] leading-5">
                      <span className="text-muted-foreground">视觉风格</span>
                      <select
                        value={stylePreset}
                        onChange={(event) => setStylePreset(event.target.value)}
                        disabled={generationPending}
                        className="h-10 w-full border border-input bg-background px-2.5 text-[13px] outline-none focus:ring-2 focus:ring-ring"
                      >
                        {IMAGE_STYLE_PRESETS.map((style) => (
                          <option key={style.id || 'none'} value={style.id}>
                            {style.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block space-y-1.5 text-[13px] leading-5">
                      <span className="text-muted-foreground">负面词</span>
                      <Input
                        value={negativePrompt}
                        onChange={(event) => setNegativePrompt(event.target.value)}
                        placeholder="例如：变形、错误 Logo、多余手指"
                        className="h-10 text-[13px]"
                        maxLength={2000}
                        disabled={generationPending}
                      />
                    </label>
                    <label className="flex items-start justify-between gap-3 text-[13px] leading-5">
                      <span>
                        <span className="block font-medium">使用品牌调性</span>
                        <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
                          注入品牌风格，并自动过滤品牌禁词
                        </span>
                      </span>
                      <input
                        type="checkbox"
                        checked={useBrandPersona}
                        onChange={(event) => setUseBrandPersona(event.target.checked)}
                        disabled={generationPending}
                        className="mt-1 h-4 w-4 accent-[var(--factory-accent)]"
                      />
                    </label>
                  </div>
                </details>
              </>
            )}

            <div className="border-t border-border pt-4 pr-20 lg:pr-0">
              <Button
                className="h-10 w-full justify-between px-4"
                onClick={() => generateMutation.mutate()}
                disabled={Boolean(validationError) || generationPending}
                title={validationError || undefined}
              >
                <span className="inline-flex items-center">
                  {generationPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 h-4 w-4" />
                  )}
                  {generationState === 'submitting'
                    ? '提交中...'
                    : generationState === 'generating'
                      ? '生成中...'
                      : mode === 'platform_white'
                        ? '生成白底图'
                        : (
                          <>生成 {numOutputs} 张</>
                        )}
                </span>
                <span className="metric-number text-xs">
                  {estimatedCredits} 积分
                </span>
              </Button>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {mode === 'platform_white'
                  ? '本地处理，不扣积分'
                  : mode === 'product_scene' && billingMode === 'free_creation'
                    ? '无参考图按文字生成，按自由创作积分计费'
                    : '生成成功后扣费'}
              </p>
            </div>
            {validationError && (
              <p className="text-[11px] text-muted-foreground">{validationError}</p>
            )}
          </div>
        </div>
      </section>

      {actionError && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {actionError}
        </div>
      )}
      {actionSuccess && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-2 rounded-md border border-[color:var(--factory-success)]/30 bg-[color:var(--factory-success)]/8 px-3 py-2 text-sm text-[var(--factory-success)]"
        >
          <Check className="h-4 w-4 shrink-0" />
          {actionSuccess}
        </div>
      )}
      {uploadMutation.isPending && (
        <div className="rounded-md border border-border bg-background p-3">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="text-muted-foreground">
              {uploadProgress >= 100 ? '文件已传完，正在优化图片...' : '正在上传图片...'}
            </span>
            <span className="metric-number">{uploadProgress}%</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden bg-secondary">
            <div
              className="h-full bg-[var(--factory-accent)] transition-[width] duration-200"
              style={{ width: `${Math.max(2, uploadProgress)}%` }}
            />
          </div>
        </div>
      )}

      <ImageEditingPanel
        assets={localAssets}
        onUpload={() => fileInputRef.current?.click()}
        onCompleted={() => {
          queryClient.invalidateQueries({ queryKey: ['image-assets'] })
          queryClient.invalidateQueries({ queryKey: ['image-generation-history'] })
        }}
      />

      <div
        className={`grid gap-4 ${
          mode === 'platform_white'
            ? 'xl:grid-cols-[minmax(0,1fr)_340px]'
            : ''
        }`}
      >
        <Card className="min-w-0 overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between gap-3 border-b border-border">
            <div className="min-w-0">
              <CardTitle className="truncate text-sm">{selected?.name || '图片预览'}</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                {selected
                  ? `${selected.width || '-'} × ${selected.height || '-'} · ${formatFileSize(selected.file_size)}`
                  : '上传或选择一张图片开始处理'}
              </p>
            </div>
            {selected && (
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  title="复制图片链接"
                  aria-label="复制图片链接"
                  onClick={copySelectedUrl}
                >
                  {copied ? <Check className="h-4 w-4 text-[var(--factory-success)]" /> : <Copy className="h-4 w-4" />}
                </Button>
                <a
                  href={selected.image_url}
                  download
                  className="inline-flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  title="下载图片"
                  aria-label="下载图片"
                >
                  <Download className="h-4 w-4" />
                </a>
                <Button
                  variant="ghost"
                  size="icon"
                  title="删除素材"
                  aria-label="删除素材"
                  disabled={deleteMutation.isPending}
                  onClick={() => setDeleteTarget(selected)}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </div>
            )}
          </CardHeader>
          <CardContent className="p-3 sm:p-5">
            {selected ? (
              <div className="space-y-3">
                <div className="flex min-h-[360px] items-center justify-center rounded-md border border-border bg-[var(--factory-raised)] p-4 sm:min-h-[520px]">
                  <img
                    src={resolveMediaUrl(selected.image_url)}
                    alt={selected.name}
                    className="max-h-[500px] max-w-full object-contain"
                  />
                </div>
                <dl className="grid gap-3 border border-border bg-background p-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                  <div>
                    <dt className="text-muted-foreground">素材来源</dt>
                    <dd className="mt-1 font-medium">
                      {selected.kind === 'upload'
                        ? '图片工作台上传'
                        : selected.kind === 'processed'
                          ? '白底图处理'
                          : 'AI 生成记录'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">尺寸</dt>
                    <dd className="metric-number mt-1 font-medium">
                      {selected.width && selected.height
                        ? `${selected.width} × ${selected.height}`
                        : '-'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">文件大小</dt>
                    <dd className="metric-number mt-1 font-medium">
                      {formatFileSize(selected.file_size)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">创建时间</dt>
                    <dd className="mt-1 font-medium">
                      {new Date(selected.created_at).toLocaleString('zh-CN')}
                    </dd>
                  </div>
                </dl>
                {(selected.prompt || selected.model) && (
                  <div className="border border-border bg-background px-3 py-2.5">
                    <p className="text-[11px] text-muted-foreground">
                      {selected.model || 'AI 图片'}
                    </p>
                    <p className="mt-1 whitespace-pre-wrap text-xs leading-6">
                      {selected.prompt || '无提示词记录'}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <button
                type="button"
                className={`flex min-h-[360px] w-full flex-col items-center justify-center rounded-md border border-dashed px-6 text-center transition-colors sm:min-h-[520px] ${
                  dragging ? 'border-primary bg-primary/5' : 'border-border bg-background/40'
                }`}
                onClick={() => fileInputRef.current?.click()}
                onDragEnter={(event) => {
                  event.preventDefault()
                  setDragging(true)
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault()
                  setDragging(false)
                  chooseFile(event.dataTransfer.files)
                }}
              >
                {uploadMutation.isPending ? (
                  <Loader2 className="mb-4 h-10 w-10 animate-spin text-primary" />
                ) : (
                  <ImagePlus className="mb-4 h-10 w-10 text-muted-foreground" />
                )}
                <p className="text-sm font-medium">
                  {uploadMutation.isPending
                    ? uploadProgress >= 100
                      ? '图片优化中，请稍候'
                      : `正在上传 ${uploadProgress}%`
                    : '点击或拖拽上传商品图片'}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">支持 JPEG、PNG、WebP，最大 12MB</p>
              </button>
            )}
          </CardContent>
        </Card>

        {mode === 'platform_white' && (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">平台白底尺寸</CardTitle>
                <p className="text-xs leading-5 text-muted-foreground">
                  仅在平台白底模式生效，用于确定最终输出画布和纯白背景尺寸。
                </p>
              </CardHeader>
              <CardContent className="space-y-2">
                {(presetsQuery.data || []).map((preset) => {
                  const active = preset.id === presetId
                  return (
                    <button
                      key={preset.id}
                      type="button"
                      className={`flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2.5 text-left transition-colors ${
                        active ? 'border-primary/60 bg-primary/5' : 'border-border hover:bg-accent'
                      }`}
                      aria-pressed={active}
                      onClick={() => setPresetId(preset.id)}
                    >
                      <span className="min-w-0">
                        <span className="block text-sm font-medium">{preset.platform} · {preset.label}</span>
                        <span className="mt-0.5 block truncate text-xs text-muted-foreground">{preset.note}</span>
                      </span>
                      <span className="metric-number shrink-0 text-xs text-muted-foreground">
                        {preset.width} × {preset.height}
                      </span>
                    </button>
                  )
                })}
              </CardContent>
            </Card>
          </div>
        )}
      </div>

      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="section-title flex items-center gap-2">
              <Grid3X3 className="h-4 w-4 text-primary" />
              素材库
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">上传图、白底成图和 AI 生成结果集中管理</p>
          </div>
          <div className="flex flex-wrap gap-1 rounded-md border bg-background p-0.5">
            {filterItems.map((item) => (
              <Button
                key={item.id}
                variant={filter === item.id ? 'secondary' : 'ghost'}
                size="sm"
                className="h-7 gap-1.5 px-2.5 text-xs"
                aria-pressed={filter === item.id}
                onClick={() => setFilter(item.id)}
              >
                {item.label}
                <span className="metric-number text-[11px] text-muted-foreground">{item.count}</span>
              </Button>
            ))}
          </div>
        </div>

        {visibleItems.length > 0 ? (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            {visibleItems.map((item) => (
              <AssetCard
                key={item.id}
                item={item}
                selected={item.id === selectedId}
                onSelect={() => setSelectedId(item.id)}
                onDelete={() => setDeleteTarget(item)}
              />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
              <ImagePlus className="mb-3 h-9 w-9 opacity-40" />
              <p className="text-sm">当前分类还没有素材</p>
              <Button variant="outline" size="sm" className="mt-4" onClick={() => fileInputRef.current?.click()}>
                <Upload className="mr-2 h-4 w-4" />
                上传第一张图片
              </Button>
            </CardContent>
          </Card>
        )}
      </section>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={deleteTarget?.taskId && !deleteTarget.assetId ? '删除 AI 图片记录？' : '删除这张图片？'}
        description={
          deleteTarget?.taskId && !deleteTarget.assetId
            ? `将删除“${deleteTarget.prompt || deleteTarget.name}”对应的整条生成记录和全部结果，此操作不可恢复。`
            : `将删除“${deleteTarget?.name || '当前素材'}”及其存储文件，引用该素材的视频任务会失去首帧关联。`
        }
        pending={deleteMutation.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget)
        }}
      />
    </motion.div>
  )
}

/** 素材卡片只负责选择与预览，删除等破坏性操作交给上层确认流程。 */
function AssetCard({
  item,
  selected,
  onSelect,
  onDelete,
}: {
  item: WorkbenchLibraryItem
  selected: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  const kindLabel = item.kind === 'upload' ? '原图' : item.kind === 'processed' ? '白底图' : 'AI 生成'

  return (
    <article
      className={`group relative overflow-hidden rounded-lg border text-left transition-colors ${
        selected ? 'border-primary bg-primary/5' : 'border-border bg-card hover:bg-accent/40'
      }`}
    >
      <button type="button" className="block w-full text-left" onClick={onSelect}>
        <div className="relative aspect-square bg-[var(--factory-raised)]">
          <img
            src={resolveMediaUrl(item.image_url)}
            alt={item.name}
            loading="lazy"
            className="h-full w-full object-contain p-2 transition-transform duration-200 group-hover:scale-[1.02]"
          />
          <Badge variant="secondary" className="absolute left-2 top-2 border border-black/10 bg-white/90 text-[11px] text-black">
            {kindLabel}
          </Badge>
        </div>
        <div className="space-y-1 p-2.5">
          <p className="truncate text-xs font-medium">{item.name}</p>
          <p className="truncate text-[11px] text-muted-foreground">
            {item.width && item.height ? `${item.width} × ${item.height}` : item.platform || '-'}
          </p>
        </div>
      </button>
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-2 top-2 z-10 h-8 w-8 bg-background/90"
        title="删除素材"
        aria-label={`删除 ${item.name}`}
        onClick={(event) => {
          event.stopPropagation()
          onDelete()
        }}
      >
        <Trash2 className="h-3.5 w-3.5 text-destructive" />
      </Button>
    </article>
  )
}
