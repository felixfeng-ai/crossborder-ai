import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Clock3,
  Download,
  FolderOpen,
  ExternalLink,
  Image as ImageIcon,
  Loader2,
  Play,
  Trash2,
  Video,
} from 'lucide-react'
import apiClient from '@/api/client'
import { resolveMediaUrl } from '@/lib/apiUrl'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import ConfirmDialog from '@/components/common/ConfirmDialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  buildImageMaterials,
  buildVideoMaterials,
  imageSourceLabel,
  type GeneratedImageHistoryInput,
  type ImageAssetInput,
  type ImageMaterial,
  type MarketingProjectInput,
  type VideoMaterial,
  type VideoTaskInput,
} from '@/lib/assets/materials'
import { formatFileSize } from '@/lib/images/workbench'
import { safeFilenamePart } from '@/lib/videos/marketing'
import { toErrorMessage } from '@/utils/errorMessage'
import { cn } from '@/utils/cn'


type ImageFilter = 'all' | ImageMaterial['source']
type VideoFilter = 'all' | VideoMaterial['source']

export default function MaterialsPage() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState('images')
  const [imageFilter, setImageFilter] = useState<ImageFilter>('all')
  const [videoFilter, setVideoFilter] = useState<VideoFilter>('all')
  const [selectedImageId, setSelectedImageId] = useState('')
  const [selectedVideoId, setSelectedVideoId] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<ImageMaterial | VideoMaterial | null>(null)
  const [actionError, setActionError] = useState('')

  const assetsQuery = useQuery<ImageAssetInput[]>({
    queryKey: ['material-image-assets'],
    queryFn: async () => {
      const response = await apiClient.get('/images/assets')
      return response.data.items || []
    },
  })

  const imageHistoryQuery = useQuery<GeneratedImageHistoryInput[]>({
    queryKey: ['material-image-history'],
    queryFn: async () => {
      const response = await apiClient.get('/images/history')
      return response.data || []
    },
  })

  const singleVideoQuery = useQuery<VideoTaskInput[]>({
    queryKey: ['material-single-videos'],
    queryFn: async () => {
      const response = await apiClient.get('/videos/history')
      return response.data || []
    },
  })

  const marketingVideoQuery = useQuery<MarketingProjectInput[]>({
    queryKey: ['material-marketing-videos'],
    queryFn: async () => {
      const response = await apiClient.get('/marketing-videos/projects')
      return response.data || []
    },
  })

  const images = useMemo(
    () => buildImageMaterials(
      assetsQuery.data || [],
      imageHistoryQuery.data || [],
    ),
    [assetsQuery.data, imageHistoryQuery.data],
  )
  const videos = useMemo(
    () => buildVideoMaterials(
      singleVideoQuery.data || [],
      marketingVideoQuery.data || [],
    ),
    [marketingVideoQuery.data, singleVideoQuery.data],
  )
  const visibleImages = imageFilter === 'all'
    ? images
    : images.filter((item) => item.source === imageFilter)
  const visibleVideos = videoFilter === 'all'
    ? videos
    : videos.filter((item) => item.source === videoFilter)
  const selectedVideo = videos.find((item) => item.id === selectedVideoId) || null
  const selectedImage = images.find((item) => item.id === selectedImageId) || null

  useEffect(() => {
    if (selectedVideoId && !videos.some((item) => item.id === selectedVideoId)) {
      setSelectedVideoId('')
    }
  }, [selectedVideoId, videos])

  useEffect(() => {
    if (!images.length) {
      if (selectedImageId) setSelectedImageId('')
      return
    }
    if (!images.some((item) => item.id === selectedImageId)) {
      setSelectedImageId(images[0].id)
    }
  }, [images, selectedImageId])

  const deleteMutation = useMutation({
    mutationFn: async (target: ImageMaterial | VideoMaterial) => {
      await apiClient.delete(target.deleteEndpoint)
    },
    onMutate: () => setActionError(''),
    onSuccess: () => {
      setDeleteTarget(null)
      setSelectedImageId('')
      setSelectedVideoId('')
      queryClient.invalidateQueries({ queryKey: ['material-image-assets'] })
      queryClient.invalidateQueries({ queryKey: ['material-image-history'] })
      queryClient.invalidateQueries({ queryKey: ['material-single-videos'] })
      queryClient.invalidateQueries({ queryKey: ['material-marketing-videos'] })
      queryClient.invalidateQueries({ queryKey: ['image-assets'] })
      queryClient.invalidateQueries({ queryKey: ['video-history'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '删除素材失败')),
  })

  const loading =
    assetsQuery.isLoading ||
    imageHistoryQuery.isLoading ||
    singleVideoQuery.isLoading ||
    marketingVideoQuery.isLoading

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <FolderOpen className="h-6 w-6 text-primary" />
            素材中心
          </h1>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
            集中查找和复用商品原图、白底图、AI 图片、商品图生视频与营销成片。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="metric-number">
            {images.length} 图片
          </Badge>
          <Badge variant="outline" className="metric-number">
            {videos.length} 视频
          </Badge>
        </div>
      </div>

      {actionError && (
        <div className="border border-destructive/35 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {actionError}
        </div>
      )}

      <section className="border border-border bg-[var(--factory-panel)]">
        <Tabs value={tab} onValueChange={setTab}>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
            <TabsList>
              <TabsTrigger value="images">图片</TabsTrigger>
              <TabsTrigger value="videos">视频</TabsTrigger>
            </TabsList>
            <p className="text-xs text-muted-foreground">
              仅展示当前账号已完成的素材
            </p>
          </div>

          {loading ? (
            <div className="flex min-h-80 items-center justify-center">
              <Loader2 className="h-7 w-7 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              <TabsContent value="images" className="m-0">
                <div className="flex flex-wrap gap-1 border-b border-border px-4 py-2">
                  <FilterButton
                    active={imageFilter === 'all'}
                    onClick={() => setImageFilter('all')}
                  >
                    全部 {images.length}
                  </FilterButton>
                  {(['upload', 'processed', 'generated'] as const).map((source) => (
                    <FilterButton
                      key={source}
                      active={imageFilter === source}
                      onClick={() => setImageFilter(source)}
                    >
                      {imageSourceLabel(source)} {images.filter((item) => item.source === source).length}
                    </FilterButton>
                  ))}
                </div>
                <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_360px]">
                  <div className="border-b border-border p-4 xl:border-b-0 xl:border-r">
                    <ImageGrid
                      items={visibleImages}
                      selectedId={selectedImageId}
                      onSelect={setSelectedImageId}
                      onDelete={setDeleteTarget}
                    />
                  </div>
                  <ImageDetail
                    material={selectedImage}
                    onDelete={setDeleteTarget}
                  />
                </div>
              </TabsContent>

              <TabsContent value="videos" className="m-0">
                <div className="flex flex-wrap gap-1 border-b border-border px-4 py-2">
                  <FilterButton
                    active={videoFilter === 'all'}
                    onClick={() => setVideoFilter('all')}
                  >
                    全部 {videos.length}
                  </FilterButton>
                  <FilterButton
                    active={videoFilter === 'marketing'}
                    onClick={() => setVideoFilter('marketing')}
                  >
                    营销成片 {videos.filter((item) => item.source === 'marketing').length}
                  </FilterButton>
                  <FilterButton
                    active={videoFilter === 'single'}
                    onClick={() => setVideoFilter('single')}
                  >
                    商品图生视频 {videos.filter((item) => item.source === 'single').length}
                  </FilterButton>
                </div>
                <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_360px]">
                  <div className="border-b border-border p-4 xl:border-b-0 xl:border-r">
                    {visibleVideos.length > 0 ? (
                      <div className="grid gap-3 sm:grid-cols-2">
                        {visibleVideos.map((videoItem) => (
                          <VideoRow
                            key={videoItem.id}
                            item={videoItem}
                            selected={selectedVideoId === videoItem.id}
                            onSelect={() => setSelectedVideoId(videoItem.id)}
                            onDelete={() => setDeleteTarget(videoItem)}
                          />
                        ))}
                      </div>
                    ) : (
                      <EmptyMaterials label="当前分类还没有视频素材" />
                    )}
                  </div>
                  <VideoPreview
                    material={selectedVideo}
                    onDelete={setDeleteTarget}
                  />
                </div>
              </TabsContent>
            </>
          )}
        </Tabs>
      </section>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={deleteTarget?.type === 'video' ? '删除视频素材？' : '删除图片素材？'}
        description={
          deleteTarget
            ? `将永久删除“${deleteTarget.name}”${
                deleteTarget.type === 'video' ? '及其本地视频文件' : '及对应素材记录'
              }，此操作不可恢复。`
            : ''
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


function ImageGrid({
  items,
  selectedId,
  onSelect,
  onDelete,
}: {
  items: ImageMaterial[]
  selectedId: string
  onSelect: (id: string) => void
  onDelete: (item: ImageMaterial) => void
}) {
  if (!items.length) {
    return <EmptyMaterials label="当前分类还没有图片素材" />;
  }
  return (
    <div className="grid grid-cols-2 gap-3 p-4 md:grid-cols-3 xl:grid-cols-5">
      {items.map((item) => (
        <article
          key={item.id}
          className={cn(
            'relative overflow-hidden border bg-background',
            selectedId === item.id
              ? 'border-[color:var(--factory-accent)] ring-1 ring-[color:var(--factory-accent)]'
              : 'border-border',
          )}
        >
          <button
            type="button"
            className="group block w-full text-left"
            onClick={() => onSelect(item.id)}
          >
            <span className="group block aspect-square overflow-hidden bg-[#d9dad5]">
              <img
                src={resolveMediaUrl(item.url)}
                alt={item.name}
                loading="lazy"
                className="h-full w-full object-contain p-2 transition-transform duration-200 group-hover:scale-[1.02]"
              />
            </span>
            <div className="space-y-1.5 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-xs font-medium">{item.name}</p>
                <Badge variant="outline" className="shrink-0 text-[10px]">
                  {imageSourceLabel(item.source)}
                </Badge>
              </div>
              <div className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                <span className="metric-number truncate">
                  {item.width && item.height
                    ? `${item.width} × ${item.height}`
                    : item.model || '图片素材'}
                </span>
                <ExternalLink className="h-3 w-3 shrink-0" />
              </div>
            </div>
          </button>
          <Button
            variant="ghost"
            size="icon"
            className="absolute right-2 top-2 z-10 h-8 w-8 bg-background/90"
            aria-label={`删除 ${item.name}`}
            title="删除素材"
            onClick={() => onDelete(item)}
          >
            <Trash2 className="h-3.5 w-3.5 text-destructive" />
          </Button>
        </article>
      ))}
    </div>
  )
}


function ImageDetail({
  material,
  onDelete,
}: {
  material: ImageMaterial | null
  onDelete: (item: ImageMaterial) => void
}) {
  return (
    <div className="p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="micro-label">图片详情</p>
        {material && (
          <div className="flex items-center gap-1">
            <a
              href={resolveMediaUrl(material.url)}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 w-8 items-center justify-center text-muted-foreground hover:text-foreground"
              aria-label="打开原图"
              title="打开原图"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
            <Button
              variant="ghost"
              size="icon"
              aria-label="删除图片素材"
              title="删除素材"
              onClick={() => onDelete(material)}
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        )}
      </div>
      <div className="mt-3 flex min-h-[360px] items-center justify-center border border-border bg-[#d9dad5]">
        {material ? (
          <img
            src={resolveMediaUrl(material.url)}
            alt={material.name}
            className="max-h-[520px] w-full object-contain p-3"
          />
        ) : (
          <div className="text-center text-xs text-muted-foreground">
            <ImageIcon className="mx-auto mb-2 h-6 w-6" />
            选择一个图片素材
          </div>
        )}
      </div>
      {material && (
        <div className="mt-3 space-y-3">
          <div>
            <p className="truncate text-sm font-medium">{material.name}</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              {imageSourceLabel(material.source)}
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="border border-border p-2">
              <dt className="text-muted-foreground">尺寸</dt>
              <dd className="metric-number mt-1">
                {material.width && material.height
                  ? `${material.width} × ${material.height}`
                  : '-'}
              </dd>
            </div>
            <div className="border border-border p-2">
              <dt className="text-muted-foreground">文件</dt>
              <dd className="metric-number mt-1">
                {formatFileSize(material.fileSize)}
              </dd>
            </div>
            <div className="border border-border p-2">
              <dt className="text-muted-foreground">模型</dt>
              <dd className="mt-1 truncate">{material.model || '-'}</dd>
            </div>
            <div className="border border-border p-2">
              <dt className="text-muted-foreground">创建时间</dt>
              <dd className="mt-1">{new Date(material.createdAt).toLocaleDateString('zh-CN')}</dd>
            </div>
          </dl>
          {material.prompt && (
            <div className="border border-border bg-background p-2.5">
              <p className="text-[10px] text-muted-foreground">生成提示词</p>
              <p className="mt-1 whitespace-pre-wrap text-xs leading-5">{material.prompt}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}


function VideoRow({
  item,
  selected,
  onSelect,
  onDelete,
}: {
  item: VideoMaterial
  selected: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  return (
    <article
      className={cn(
        'relative flex min-h-24 items-center gap-3 border p-3 text-left transition-colors',
        selected
          ? 'border-[color:var(--factory-accent)] bg-[color:var(--factory-accent)]/5'
          : 'border-border hover:bg-accent/50',
      )}
    >
      <button
        type="button"
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
        onClick={onSelect}
      >
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-border bg-secondary">
          <Play className="ml-0.5 h-4 w-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate pr-7 text-sm font-medium">{item.name}</span>
          <span className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
            <span>{item.source === 'marketing' ? '营销成片' : '商品图生视频'}</span>
            <span>·</span>
            <span className="metric-number">{item.duration}s</span>
            <span>·</span>
            <span className="metric-number">{item.resolution}</span>
          </span>
        </span>
      </button>
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-2 top-2 h-8 w-8"
        aria-label={`删除 ${item.name}`}
        title="删除视频"
        onClick={onDelete}
      >
        <Trash2 className="h-3.5 w-3.5 text-destructive" />
      </Button>
    </article>
  )
}


function VideoPreview({
  material,
  onDelete,
}: {
  material: VideoMaterial | null
  onDelete: (item: VideoMaterial) => void
}) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    setError('')
    setUrl('')
    if (!material) return
    const controller = new AbortController()
    let objectUrl = ''
    apiClient
      .get(material.fileEndpoint, {
        responseType: 'blob',
        signal: controller.signal,
      })
      .then((response) => {
        objectUrl = URL.createObjectURL(response.data)
        setUrl(objectUrl)
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(toErrorMessage(reason, '视频加载失败'))
        }
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [material])

  const download = async () => {
    if (!material) return
    setDownloading(true)
    setError('')
    try {
      const response = await apiClient.get(material.fileEndpoint, {
        responseType: 'blob',
      })
      const objectUrl = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = `${safeFilenamePart(material.name, '商品视频')}-${
        material.source === 'marketing' ? '营销成片' : '商品图生视频'
      }.mp4`
      link.click()
      URL.revokeObjectURL(objectUrl)
    } catch (reason) {
      setError(toErrorMessage(reason, '视频下载失败'))
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="micro-label">视频预览</p>
        {material && (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={download}
              disabled={downloading}
              aria-label="下载视频"
              title="下载视频"
            >
              {downloading
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <Download className="h-4 w-4" />}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onDelete(material)}
              aria-label="删除视频素材"
              title="删除视频"
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        )}
      </div>
      <div className="mt-3 flex min-h-[360px] items-center justify-center border border-border bg-[var(--factory-ground)]">
        {!material ? (
          <div className="text-center text-xs text-muted-foreground">
            <Video className="mx-auto mb-2 h-6 w-6" />
            选择一个视频素材
          </div>
        ) : error ? (
          <p className="px-6 text-center text-xs text-destructive">{error}</p>
        ) : url ? (
          <video
            key={url}
            src={url}
            controls
            playsInline
            className="max-h-[520px] w-full bg-black object-contain"
          />
        ) : (
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        )}
      </div>
      {material && (
        <div className="mt-3 space-y-2">
          <div className="flex items-center justify-between gap-3 text-[11px] text-muted-foreground">
            <span className="truncate">{material.name}</span>
            <span className="metric-number shrink-0 flex items-center gap-1">
              <Clock3 className="h-3 w-3" />
              {material.duration}s · {material.resolution}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="border border-border p-2">
              <p className="text-muted-foreground">素材来源</p>
              <p className="mt-1">
                {material.source === 'marketing' ? '营销成片项目' : '商品图生视频任务'}
              </p>
            </div>
            <div className="border border-border p-2">
              <p className="text-muted-foreground">模型</p>
              <p className="mt-1 truncate">{material.model}</p>
            </div>
            <div className="border border-border p-2">
              <p className="text-muted-foreground">创建时间</p>
              <p className="mt-1">{new Date(material.createdAt).toLocaleDateString('zh-CN')}</p>
            </div>
            <div className="border border-border p-2">
              <p className="text-muted-foreground">文件</p>
              <p className="mt-1">MP4</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <Button
      type="button"
      variant={active ? 'secondary' : 'ghost'}
      size="sm"
      className="h-7 px-2.5 text-xs"
      aria-pressed={active}
      onClick={onClick}
    >
      {children}
    </Button>
  )
}


function EmptyMaterials({ label }: { label: string }) {
  return (
    <div className="flex min-h-44 flex-col items-center justify-center text-center">
      <ImageIcon className="mb-3 h-7 w-7 text-muted-foreground/50" />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  )
}
