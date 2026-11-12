import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  CircleAlert,
  Clock3,
  Download,
  Film,
  Image as ImageIcon,
  Loader2,
  Play,
  Sparkles,
  Square,
  Trash2,
  Video,
} from 'lucide-react'
import apiClient from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import ConfirmDialog from '@/components/common/ConfirmDialog'
import { Label } from '@/components/ui/label'
import {
  estimateVideoCredits,
  formatVideoDuration,
  getVideoModel,
  isVideoTerminal,
  videoStatusLabel,
  type VideoCapabilities,
  type VideoTask,
} from '@/lib/videos/workbench'
import { toErrorMessage } from '@/utils/errorMessage'
import { cn } from '@/utils/cn'
import { resolveMediaUrl } from '@/lib/apiUrl'

interface SourceAsset {
  id: string
  name: string
  kind: string
  image_url: string
  width: number
  height: number
}

const DURATION_OPTIONS = [4, 6, 8, 10, 15]

export default function VideosPage({ embedded = false }: { embedded?: boolean }) {
  const queryClient = useQueryClient()
  const [sourceAssetId, setSourceAssetId] = useState('')
  const [selectedTaskId, setSelectedTaskId] = useState('')
  const [templateId, setTemplateId] = useState('clean_product')
  const [modelId, setModelId] = useState('MiniMax-H3-Lite')
  const [resolution, setResolution] = useState('480P')
  const [duration, setDuration] = useState(4)
  const [prompt, setPrompt] = useState('')
  const [actionError, setActionError] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<VideoTask | null>(null)

  const capabilitiesQuery = useQuery<VideoCapabilities>({
    queryKey: ['video-capabilities'],
    queryFn: async () => {
      const response = await apiClient.get('/videos/capabilities')
      return response.data
    },
  })

  const assetsQuery = useQuery<SourceAsset[]>({
    queryKey: ['image-assets'],
    queryFn: async () => {
      const response = await apiClient.get('/images/assets')
      return response.data.items || []
    },
  })

  const hasActiveTask = (task: VideoTask) => !isVideoTerminal(task.status)
  const historyQuery = useQuery<VideoTask[]>({
    queryKey: ['video-history'],
    queryFn: async () => {
      const response = await apiClient.get('/videos/history')
      return response.data || []
    },
    refetchInterval: (query) => {
      const tasks = query.state.data as VideoTask[] | undefined
      return tasks?.some(hasActiveTask) ? 3000 : false
    },
  })

  const capabilities = capabilitiesQuery.data
  const assets = assetsQuery.data || []
  const history = historyQuery.data || []
  const selectedAsset = assets.find((asset) => asset.id === sourceAssetId) || null
  const selectedTask = history.find((task) => task.id === selectedTaskId) || null
  const selectedTemplate = capabilities?.templates.find(
    (template) => template.id === templateId,
  )
  const currentModel = getVideoModel(capabilities, modelId)
  const credits = estimateVideoCredits(capabilities, modelId, resolution, duration)

  useEffect(() => {
    if (!capabilities) return
    if (!getVideoModel(capabilities, modelId)) {
      setModelId(capabilities.default_model)
    }
  }, [capabilities, modelId])

  useEffect(() => {
    if (!currentModel) return
    if (!currentModel.resolutions.includes(resolution)) {
      setResolution(currentModel.resolutions[0] || '480P')
    }
    if (duration < currentModel.min_duration || duration > currentModel.max_duration) {
      setDuration(currentModel.min_duration)
    }
  }, [currentModel, duration, resolution])

  useEffect(() => {
    if (!assets.length) {
      if (sourceAssetId) setSourceAssetId('')
      return
    }
    if (!assets.some((asset) => asset.id === sourceAssetId)) {
      setSourceAssetId(assets[0].id)
    }
  }, [assets, sourceAssetId])

  useEffect(() => {
    if (!history.length) {
      if (selectedTaskId) setSelectedTaskId('')
      return
    }
    if (!history.some((task) => task.id === selectedTaskId)) {
      setSelectedTaskId(history[0].id)
    }
  }, [history, selectedTaskId])

  const generateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedAsset) throw new Error('请先选择商品首帧')
      const response = await apiClient.post<VideoTask>(
        '/videos/generate',
        {
          source_asset_id: selectedAsset.id,
          prompt,
          template_id: templateId,
          model: modelId,
          resolution,
          duration,
          ratio: '9:16',
        },
        {
          headers: { 'Idempotency-Key': crypto.randomUUID() },
        },
      )
      return response.data
    },
    onMutate: () => setActionError(''),
    onSuccess: (task) => {
      setSelectedTaskId(task.id)
      queryClient.invalidateQueries({ queryKey: ['video-history'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '视频任务提交失败')),
  })

  const cancelMutation = useMutation({
    mutationFn: async (taskId: string) => {
      const response = await apiClient.post(`/videos/tasks/${taskId}/cancel`)
      return response.data as VideoTask
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['video-history'] }),
    onError: (error) => setActionError(toErrorMessage(error, '取消任务失败')),
  })

  const deleteMutation = useMutation({
    mutationFn: async (task: VideoTask) => {
      await apiClient.delete(`/videos/tasks/${task.id}`)
    },
    onMutate: () => setActionError(''),
    onSuccess: () => {
      setDeleteTarget(null)
      setSelectedTaskId('')
      queryClient.invalidateQueries({ queryKey: ['video-history'] })
      queryClient.invalidateQueries({ queryKey: ['material-single-videos'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '删除视频失败')),
  })

  const downloadVideo = async () => {
    if (!selectedTask || selectedTask.status !== 'succeeded') return
    try {
      const response = await apiClient.get(
        `/videos/tasks/${selectedTask.id}/file`,
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = `veyaship-${selectedTask.id}.mp4`
      link.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      setActionError(toErrorMessage(error, '视频下载失败'))
    }
  }

  const submitDisabled =
    !capabilities?.enabled ||
    !selectedAsset ||
    !templateId ||
    !currentModel?.resolutions.includes(resolution) ||
    generateMutation.isPending

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      {!embedded && (
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="page-title flex items-center gap-2">
              <Film className="h-6 w-6 text-primary" />
              商品图生视频
            </h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              用商品首帧生成 9:16 短视频，锁定商品外观，只改变镜头、光影与背景。
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2">
            <span className="status-dot" />
            <span className="text-xs text-muted-foreground">
              {capabilities?.enabled ? 'MiniMax H3 已就绪' : '视频服务待配置'}
            </span>
          </div>
        </div>
      )}

      {!capabilitiesQuery.isLoading && capabilities && !capabilities.enabled && (
        <div className="flex items-start gap-3 border border-[color:var(--factory-coral)]/35 bg-[color:var(--factory-coral)]/8 px-4 py-3">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--factory-coral)]" />
          <div>
            <p className="text-sm font-medium">视频服务暂不可用</p>
            <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
              管理员需要在服务端配置 MiniMax API Key 后才能生成视频。
            </p>
          </div>
        </div>
      )}

      {actionError && (
        <div className="border border-destructive/35 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {actionError}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_370px]">
        <section className="min-w-0 border border-border bg-[var(--factory-panel)]">
          <div className="flex min-h-[58px] flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold">
                {selectedTask ? `视频任务 · ${selectedTask.id.slice(0, 8)}` : '成片预览'}
              </h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {selectedTask
                  ? `${selectedTask.model} · ${selectedTask.resolution} · ${formatVideoDuration(selectedTask.duration)}`
                  : '选择首帧并提交后，这里会显示生成进度与成片'}
              </p>
            </div>
            {selectedTask && (
              <div className="flex shrink-0 items-center gap-1">
                <Badge variant={selectedTask.status === 'succeeded' ? 'secondary' : 'outline'}>
                  {videoStatusLabel(selectedTask.status)}
                </Badge>
                {selectedTask.status === 'succeeded' && (
                  <Button
                    variant="ghost"
                    size="icon"
                    title="下载视频"
                    aria-label="下载视频"
                    onClick={downloadVideo}
                  >
                    <Download className="h-4 w-4" />
                  </Button>
                )}
              </div>
            )}
          </div>

          <div className="flex min-h-[360px] items-center justify-center bg-[var(--factory-ground)] p-4 sm:min-h-[560px]">
            <VideoPreview task={selectedTask} sourceAsset={selectedAsset} />
          </div>

          {selectedTask && !isVideoTerminal(selectedTask.status) && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin text-[color:var(--factory-accent)]" />
                供应商正在生成，页面会自动刷新
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => cancelMutation.mutate(selectedTask.id)}
                disabled={cancelMutation.isPending}
              >
                <Square className="mr-2 h-3.5 w-3.5" />
                取消任务
              </Button>
            </div>
          )}

          {selectedTask?.status === 'failed' && selectedTask.error && (
            <div className="border-t border-destructive/30 bg-destructive/8 px-4 py-3 text-sm text-destructive">
              {selectedTask.error}
            </div>
          )}
        </section>

        <section className="border border-border bg-[var(--factory-panel)]">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold">生成参数</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">一次只处理一个商品镜头</p>
          </div>

          <div className="space-y-6 p-4">
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <Label>商品首帧</Label>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{assets.length} 张素材</span>
                  <a href="/app/images" className="text-foreground underline underline-offset-2">
                    管理素材
                  </a>
                </div>
              </div>
              {assets.length > 0 ? (
                <div className="grid grid-cols-4 gap-2">
                  {assets.slice(0, 8).map((asset) => (
                    <button
                      key={asset.id}
                      type="button"
                      title={asset.name}
                      aria-label={`选择首帧 ${asset.name}`}
                      aria-pressed={sourceAssetId === asset.id}
                      className={cn(
                        'aspect-square overflow-hidden border bg-[#d9dad5] transition-colors',
                        sourceAssetId === asset.id
                          ? 'border-[color:var(--factory-accent)] ring-1 ring-[color:var(--factory-accent)]'
                          : 'border-border hover:border-[color:var(--factory-line-strong)]',
                      )}
                      onClick={() => setSourceAssetId(asset.id)}
                    >
                      <img
                        src={resolveMediaUrl(asset.image_url)}
                        alt={asset.name}
                        className="h-full w-full object-contain p-1"
                      />
                    </button>
                  ))}
                </div>
              ) : (
                <a
                  href="/app/images"
                  className="flex min-h-24 items-center justify-center gap-2 border border-dashed border-border text-sm text-muted-foreground hover:text-foreground"
                >
                  <ImageIcon className="h-4 w-4" />
                  先到图片工作台上传商品图
                </a>
              )}
              {assets.length > 0 && (
                <p className="text-[10px] leading-4 text-muted-foreground">
                  首帧来自图片工作台的上传图和白底图。点击缩略图即可更换。
                </p>
              )}
            </div>

            <div className="space-y-2.5">
              <Label>镜头模板</Label>
              <div className="grid grid-cols-3 gap-1 border border-border p-0.5">
                {(capabilities?.templates || []).map((template) => (
                  <Button
                    key={template.id}
                    type="button"
                    variant={templateId === template.id ? 'secondary' : 'ghost'}
                    size="sm"
                    className="h-auto min-h-9 px-2 text-center text-xs"
                    aria-pressed={templateId === template.id}
                    onClick={() => setTemplateId(template.id)}
                  >
                    {template.name}
                  </Button>
                ))}
              </div>
              <p className="min-h-10 text-xs leading-5 text-muted-foreground">
                {selectedTemplate?.description}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="video-model">模型</Label>
                <select
                  id="video-model"
                  value={modelId}
                  onChange={(event) => setModelId(event.target.value)}
                  className="h-10 w-full border border-input bg-background px-2.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                >
                  {(capabilities?.models || []).map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.id.replace('MiniMax-', '')}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="video-duration">时长</Label>
                <select
                  id="video-duration"
                  value={duration}
                  onChange={(event) => setDuration(Number(event.target.value))}
                  className="metric-number h-10 w-full border border-input bg-background px-2.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                >
                  {DURATION_OPTIONS.filter(
                    (value) =>
                      !currentModel ||
                      (value >= currentModel.min_duration && value <= currentModel.max_duration),
                  ).map((value) => (
                    <option key={value} value={value}>
                      {value} 秒
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="space-y-2.5">
              <Label>清晰度</Label>
              <div className="grid grid-cols-3 gap-1 border border-border p-0.5">
                {(currentModel?.resolutions || []).map((item) => (
                  <Button
                    key={item}
                    type="button"
                    variant={resolution === item ? 'secondary' : 'ghost'}
                    size="sm"
                    className="metric-number h-8 text-xs"
                    aria-pressed={resolution === item}
                    onClick={() => setResolution(item)}
                  >
                    {item}
                  </Button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="video-prompt">镜头补充说明</Label>
              <textarea
                id="video-prompt"
                value={prompt}
                maxLength={3000}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="例如：暖光背景，镜头从正面缓慢推进，商品保持不动"
                className="min-h-24 w-full resize-y border border-input bg-background px-3 py-2 text-sm leading-6 outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
              />
              <p className="text-xs leading-5 text-muted-foreground">
                商品形状、颜色、材质、Logo 与包装文字会自动锁定。
              </p>
            </div>

            <div className="flex items-center justify-between border-t border-border pt-4">
              <div>
                <p className="text-xs text-muted-foreground">预计消耗</p>
                <p className="metric-number mt-1 text-lg font-medium">{credits} 积分</p>
              </div>
              <Button
                onClick={() => generateMutation.mutate()}
                disabled={submitDisabled}
                className="min-w-32"
              >
                {generateMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="mr-2 h-4 w-4" />
                )}
                {generateMutation.isPending ? '提交中...' : '生成视频'}
              </Button>
            </div>
          </div>
        </section>
      </div>

      <section className="space-y-3">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="section-title flex items-center gap-2">
              <Video className="h-4 w-4 text-primary" />
              视频素材库
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">生成任务与成片集中管理</p>
          </div>
          <span className="metric-number text-xs text-muted-foreground">{history.length} 条</span>
        </div>

        {history.length > 0 ? (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            {history.map((task) => (
              <article
                key={task.id}
                className={cn(
                  'relative overflow-hidden border text-left transition-colors',
                  selectedTaskId === task.id
                    ? 'border-[color:var(--factory-accent)] bg-[color:var(--factory-accent)]/5'
                    : 'border-border bg-[var(--factory-panel)] hover:bg-accent/50',
                )}
              >
                <button
                  type="button"
                  className="block w-full text-left"
                  onClick={() => setSelectedTaskId(task.id)}
                >
                  <div className="relative flex aspect-[9/12] items-center justify-center overflow-hidden bg-[var(--factory-ground)]">
                    <div className="flex h-14 w-14 items-center justify-center rounded-full border border-border bg-secondary">
                      {task.status === 'running' || task.status === 'queued' ? (
                        <Loader2 className="h-5 w-5 animate-spin text-[color:var(--factory-accent)]" />
                      ) : task.status === 'succeeded' ? (
                        <Play className="ml-0.5 h-5 w-5" />
                      ) : (
                        <CircleAlert className="h-5 w-5 text-[color:var(--factory-coral)]" />
                      )}
                    </div>
                    <Badge
                      variant="secondary"
                      className="absolute left-2 top-2 border border-border bg-background/90 text-[10px]"
                    >
                      {videoStatusLabel(task.status)}
                    </Badge>
                  </div>
                  <div className="space-y-1 p-2.5">
                    <p className="truncate pr-7 text-xs font-medium">{task.model}</p>
                    <p className="metric-number flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Clock3 className="h-3 w-3" />
                      {task.duration}s · {task.resolution}
                    </p>
                  </div>
                </button>
                {!hasActiveTask(task) && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute right-2 top-2 h-8 w-8 bg-background/90"
                    aria-label={`删除视频 ${task.id}`}
                    title="删除视频素材"
                    onClick={() => setDeleteTarget(task)}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                )}
              </article>
            ))}
          </div>
        ) : (
          <div className="flex min-h-32 flex-col items-center justify-center border border-dashed border-border text-center">
            <Film className="mb-2 h-7 w-7 text-muted-foreground/60" />
            <p className="text-sm text-muted-foreground">还没有视频素材</p>
          </div>
        )}
      </section>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="删除视频素材？"
        description={`将删除视频任务“${deleteTarget?.id.slice(0, 8) || ''}”及其本地 MP4，此操作不可恢复。营销项目镜头请从素材中心删除整个项目。`}
        pending={deleteMutation.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget)
        }}
      />
    </motion.div>
  )
}

function VideoPreview({
  task,
  sourceAsset,
}: {
  task: VideoTask | null
  sourceAsset: SourceAsset | null
}) {
  const [videoUrl, setVideoUrl] = useState('')
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    setLoadError('')
    if (!task || task.status !== 'succeeded') {
      setVideoUrl('')
      return
    }

    const controller = new AbortController()
    let objectUrl = ''
    apiClient
      .get(`/videos/tasks/${task.id}/file`, {
        responseType: 'blob',
        signal: controller.signal,
      })
      .then((response) => {
        objectUrl = URL.createObjectURL(response.data)
        setVideoUrl(objectUrl)
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setLoadError(toErrorMessage(error, '视频加载失败'))
        }
      })

    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [task])

  if (videoUrl) {
    return (
      <video
        key={videoUrl}
        src={videoUrl}
        controls
        playsInline
        className="max-h-[340px] w-full max-w-[390px] bg-black object-contain sm:max-h-[560px]"
      />
    )
  }

  if (loadError) {
    return (
      <div className="flex max-w-[320px] flex-col items-center text-center text-sm text-destructive">
        <CircleAlert className="mb-3 h-7 w-7" />
        {loadError}
      </div>
    )
  }

  if (task?.status === 'succeeded') {
    return (
      <div className="flex flex-col items-center text-sm text-muted-foreground">
        <Loader2 className="mb-3 h-7 w-7 animate-spin" />
        正在加载成片
      </div>
    )
  }

  if (task) {
    return (
      <div className="relative flex aspect-[9/16] max-h-[340px] w-full max-w-[215px] items-center justify-center overflow-hidden border border-border bg-[#171816] sm:max-h-[560px] sm:max-w-[315px]">
        {sourceAsset && (
          <img
            src={resolveMediaUrl(sourceAsset.image_url)}
            alt={sourceAsset.name}
            className="h-full w-full object-contain p-4 opacity-35"
          />
        )}
        <div className="absolute inset-x-5 bottom-5 border border-border bg-background/95 px-4 py-3">
          <div className="flex items-center gap-2">
            {(task.status === 'running' || task.status === 'queued') && (
              <Loader2 className="h-4 w-4 animate-spin text-[color:var(--factory-accent)]" />
            )}
            <p className="text-sm font-medium">{videoStatusLabel(task.status)}</p>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {task.status === 'failed'
              ? task.error || '生成失败，请调整素材或提示词后重试'
              : '成片完成后会在这里自动播放'}
          </p>
        </div>
      </div>
    )
  }

  if (sourceAsset) {
    return (
      <div className="flex aspect-[9/16] max-h-[340px] w-full max-w-[230px] items-center justify-center overflow-hidden border border-border bg-[var(--factory-panel)] sm:max-h-[560px] sm:max-w-[315px]">
        <img
          src={resolveMediaUrl(sourceAsset.image_url)}
          alt={sourceAsset.name}
          className="h-full w-full object-contain p-4"
        />
      </div>
    )
  }

  return (
    <div className="flex max-w-[300px] flex-col items-center text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center border border-border bg-secondary">
        <Video className="h-6 w-6 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium">选择一张商品首帧</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">
        首帧决定商品外观，建议使用清晰、主体完整的正面图。
      </p>
    </div>
  )
}
