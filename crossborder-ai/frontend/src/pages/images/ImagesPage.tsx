import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
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
  WandSparkles,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import ConfirmDialog from '@/components/common/ConfirmDialog'
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
  validateImageUpload,
} from '@/lib/images/upload'

interface PlatformPreset {
  id: string
  platform: string
  label: string
  width: number
  height: number
  note: string
}

type LibraryFilter = 'all' | 'upload' | 'processed' | 'generated'

export default function ImagesPage() {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedId, setSelectedId] = useState('')
  const [presetId, setPresetId] = useState('amazon-main')
  const [filter, setFilter] = useState<LibraryFilter>('all')
  const [copied, setCopied] = useState(false)
  const [showGenerate, setShowGenerate] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [actionError, setActionError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<WorkbenchLibraryItem | null>(null)

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

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const response = await apiClient.post<WorkbenchAsset>(
        '/images/assets/upload',
        formData,
        { timeout: 60_000 },
      )
      return response.data
    },
    onMutate: () => setActionError(''),
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: ['image-assets'] })
      setSelectedId(asset.id)
    },
    onError: (error) => setActionError(imageUploadErrorMessage(error)),
  })

  const processMutation = useMutation({
    mutationFn: async () => {
      if (!selectedAsset) throw new Error('请先选择一个本地素材')
      const response = await apiClient.post<WorkbenchAsset>(
        `/images/assets/${selectedAsset.id}/process`,
        { preset_id: presetId },
      )
      return response.data
    },
    onMutate: () => setActionError(''),
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: ['image-assets'] })
      setSelectedId(asset.id)
    },
    onError: (error) => setActionError(toErrorMessage(error, '白底图生成失败')),
  })

  const deleteMutation = useMutation({
    mutationFn: async (item: WorkbenchLibraryItem) => {
      if (item.kind === 'generated') {
        if (!item.taskId) throw new Error('AI 图片记录缺少任务 ID')
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

  const generateMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/images/generate', {
        prompt,
        num_outputs: 1,
      })
      return waitForImageTask(
        response.data.task_id,
        async (taskId): Promise<ImageTaskStatus> => {
          const status = await apiClient.get(`/images/status/${taskId}`)
          return status.data
        },
      )
    },
    onMutate: () => setActionError(''),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['image-generation-history'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, 'AI 图片生成失败')),
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

  const filterItems: Array<{ id: LibraryFilter; label: string; count: number }> = [
    { id: 'all', label: '全部', count: items.length },
    { id: 'upload', label: '上传', count: items.filter((item) => item.kind === 'upload').length },
    { id: 'processed', label: '白底图', count: items.filter((item) => item.kind === 'processed').length },
    { id: 'generated', label: 'AI 生成', count: items.filter((item) => item.kind === 'generated').length },
  ]

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
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

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Images className="h-6 w-6 text-primary" />
            商品图片工作台
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            上传原图、整理素材，并按平台尺寸生成白底适配图。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => setShowGenerate((value) => !value)}>
            <Sparkles className="mr-2 h-4 w-4" />
            AI 生成图片
          </Button>
          <Button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending}
          >
            {uploadMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Upload className="mr-2 h-4 w-4" />
            )}
            上传图片
          </Button>
        </div>
      </div>

      {showGenerate && (
        <Card className="border-primary/20 bg-primary/5">
          <CardContent className="flex flex-col gap-3 pt-5 md:flex-row md:items-end">
            <div className="min-w-0 flex-1 space-y-2">
              <label htmlFor="image-prompt" className="text-sm font-medium">AI 图片描述</label>
              <Input
                id="image-prompt"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="例如：白底摄影棚中的银色保温杯，柔和轮廓光"
                disabled={generateMutation.isPending}
              />
            </div>
            <Button
              className="md:shrink-0"
              onClick={() => generateMutation.mutate()}
              disabled={prompt.trim().length < 5 || generateMutation.isPending}
            >
              {generateMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-2 h-4 w-4" />
              )}
              {generateMutation.isPending ? '生成中...' : '生成并入库'}
            </Button>
          </CardContent>
        </Card>
      )}

      {actionError && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {actionError}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
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
                  {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
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
                <div className="flex min-h-[360px] items-center justify-center rounded-md border border-border bg-[#d9dad5] p-4 sm:min-h-[520px]">
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
                <p className="text-sm font-medium">{uploadMutation.isPending ? '正在上传图片' : '点击或拖拽上传商品图片'}</p>
                <p className="mt-1 text-xs text-muted-foreground">支持 JPEG、PNG、WebP，最大 12MB</p>
              </button>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">平台尺寸预设</CardTitle>
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

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <WandSparkles className="h-4 w-4 text-primary" />
                白底适配
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs leading-5 text-muted-foreground">
                等比缩放并居中，透明区域填充纯白；不会裁切或拉伸商品主体。
              </p>
              {selectedPreset && (
                <div className="rounded-md border bg-background px-3 py-2">
                  <p className="text-xs text-muted-foreground">输出尺寸</p>
                  <p className="metric-number mt-1 text-sm">{selectedPreset.width} × {selectedPreset.height}</p>
                </div>
              )}
              <Button
                className="w-full"
                onClick={() => processMutation.mutate()}
                disabled={!selectedAsset || processMutation.isPending}
              >
                {processMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <WandSparkles className="mr-2 h-4 w-4" />
                )}
                {processMutation.isPending ? '处理中...' : '生成白底图'}
              </Button>
              {!selectedAsset && selected?.kind === 'generated' && (
                <p className="text-xs text-muted-foreground">AI 生成图需先下载并重新上传后才能做白底适配。</p>
              )}
            </CardContent>
          </Card>
        </div>
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
                <span className="metric-number text-[10px] text-muted-foreground">{item.count}</span>
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
        title={deleteTarget?.kind === 'generated' ? '删除 AI 图片记录？' : '删除这张图片？'}
        description={
          deleteTarget?.kind === 'generated'
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
        <div className="relative aspect-square bg-[#d9dad5]">
          <img
            src={resolveMediaUrl(item.image_url)}
            alt={item.name}
            loading="lazy"
            className="h-full w-full object-contain p-2 transition-transform duration-200 group-hover:scale-[1.02]"
          />
          <Badge variant="secondary" className="absolute left-2 top-2 border border-black/10 bg-white/90 text-[10px] text-black">
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
