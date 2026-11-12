import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  CircleAlert,
  FileText,
  Film,
  Image as ImageIcon,
  Loader2,
  Play,
  ScanLine,
  Square,
} from 'lucide-react'
import apiClient from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { resolveMediaUrl } from '@/lib/apiUrl'
import {
  projectStatusLabel,
  shotStatusLabel,
  type MarketingCapabilities,
  type MarketingVideoProject,
} from '@/lib/videos/marketing'
import {
  formatStoryboardTime,
  storyboardConstraintLabels,
  storyboardSummary,
  type StoryboardContinuity,
} from '@/lib/videos/storyboard'
import { toErrorMessage } from '@/utils/errorMessage'
import { cn } from '@/utils/cn'
import { MarketingVideoPreview } from './MarketingVideosPage'


interface SourceAsset {
  id: string
  name: string
  image_url: string
  width: number
  height: number
}

interface ParsedStoryboardShot {
  position: number
  title: string
  source_text: string
  start_seconds: number
  end_seconds: number
  duration: number
}

interface ParsedStoryboard {
  title: string
  shot_count: number
  total_duration: number
  shots: ParsedStoryboardShot[]
  global_constraints: string
  no_dialogue: boolean
  no_subtitles: boolean
  no_watermark: boolean
  preamble: string
}


export default function ProfessionalStoryboardPage() {
  const queryClient = useQueryClient()
  const [script, setScript] = useState('')
  const [parsed, setParsed] = useState<ParsedStoryboard | null>(null)
  const [selectedAssetId, setSelectedAssetId] = useState('')
  const [productName, setProductName] = useState('')
  const [platform, setPlatform] = useState('tiktok')
  const [market, setMarket] = useState('US')
  const [language, setLanguage] = useState('en')
  const [modelId, setModelId] = useState('MiniMax-H3-Lite')
  const [resolution, setResolution] = useState('480P')
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [activeProject, setActiveProject] = useState<MarketingVideoProject | null>(null)
  const [actionError, setActionError] = useState('')

  const capabilitiesQuery = useQuery<MarketingCapabilities>({
    queryKey: ['storyboard-capabilities'],
    queryFn: async () => {
      const response = await apiClient.get('/marketing-videos/capabilities')
      return response.data
    },
  })

  const assetsQuery = useQuery<SourceAsset[]>({
    queryKey: ['storyboard-image-assets'],
    queryFn: async () => {
      const response = await apiClient.get('/images/assets')
      return response.data.items || []
    },
  })

  const historyQuery = useQuery<MarketingVideoProject[]>({
    queryKey: ['storyboard-projects'],
    queryFn: async () => {
      const response = await apiClient.get('/marketing-videos/projects', {
        params: { limit: 50 },
      })
      return (response.data || []).filter(
        (project: MarketingVideoProject) => project.mode === 'script',
      )
    },
    refetchInterval: (query) => {
      const projects = query.state.data as MarketingVideoProject[] | undefined
      return projects?.some((project) => project.status === 'rendering') ? 3000 : false
    },
  })

  const projectQuery = useQuery<MarketingVideoProject>({
    queryKey: ['storyboard-project', selectedProjectId],
    queryFn: async () => {
      const response = await apiClient.get(
        `/marketing-videos/projects/${selectedProjectId}`,
      )
      return response.data
    },
    enabled: Boolean(selectedProjectId),
    refetchInterval: (query) => {
      const project = query.state.data as MarketingVideoProject | undefined
      return project?.status === 'rendering' ? 3000 : false
    },
  })

  const capabilities = capabilitiesQuery.data
  const assets = assetsQuery.data || []
  const history = historyQuery.data || []
  const project = activeProject || projectQuery.data || null
  const selectedAsset = assets.find((asset) => asset.id === selectedAssetId) || null
  const currentModel = capabilities?.models.find((item) => item.id === modelId)

  useEffect(() => {
    if (projectQuery.data) {
      setActiveProject(projectQuery.data)
      if (projectQuery.data.status === 'succeeded') {
        queryClient.invalidateQueries({ queryKey: ['storyboard-projects'] })
      }
    }
  }, [projectQuery.data, queryClient])

  useEffect(() => {
    if (!capabilities) return
    if (!capabilities.models.some((item) => item.id === modelId)) {
      setModelId(capabilities.default_model)
    }
  }, [capabilities, modelId])

  useEffect(() => {
    if (!currentModel) return
    if (!currentModel.resolutions.includes(resolution)) {
      setResolution(currentModel.resolutions[0] || capabilities?.default_resolution || '480P')
    }
  }, [capabilities?.default_resolution, currentModel, resolution])

  useEffect(() => {
    if (!assets.length) {
      if (selectedAssetId) setSelectedAssetId('')
      return
    }
    if (!assets.some((asset) => asset.id === selectedAssetId)) {
      setSelectedAssetId(assets[0].id)
      if (!productName.trim()) setProductName(assets[0].name)
    }
  }, [assets, productName, selectedAssetId])

  useEffect(() => {
    if (selectedProjectId || !history.length) return
    setSelectedProjectId(history[0].id)
    setActiveProject(history[0])
  }, [history, selectedProjectId])

  const previewMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post<ParsedStoryboard>(
        '/marketing-videos/storyboards/preview',
        { script },
      )
      return response.data
    },
    onMutate: () => setActionError(''),
    onSuccess: (result) => setParsed(result),
    onError: (error) => setActionError(toErrorMessage(error, '分镜解析失败')),
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!selectedAsset) throw new Error('请先选择商品首帧')
      const response = await apiClient.post<MarketingVideoProject>(
        '/marketing-videos/storyboards/projects',
        {
          source_asset_id: selectedAsset.id,
          product_name: productName,
          script,
          platform,
          market,
          language,
          model: modelId,
          resolution,
        },
        { headers: { 'Idempotency-Key': crypto.randomUUID() } },
      )
      return response.data
    },
    onMutate: () => setActionError(''),
    onSuccess: (created) => {
      setSelectedProjectId(created.id)
      setActiveProject(created)
      queryClient.invalidateQueries({ queryKey: ['storyboard-projects'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '专业分镜项目创建失败')),
  })

  const renderMutation = useMutation({
    mutationFn: async (projectId: string) => {
      const response = await apiClient.post(
        `/marketing-videos/projects/${projectId}/render`,
      )
      return response.data as MarketingVideoProject
    },
    onMutate: () => setActionError(''),
    onSuccess: (rendered) => {
      setActiveProject(rendered)
      queryClient.invalidateQueries({ queryKey: ['storyboard-projects'] })
      queryClient.invalidateQueries({
        queryKey: ['storyboard-project', rendered.id],
      })
    },
    onError: (error) => setActionError(toErrorMessage(error, '分镜渲染提交失败')),
  })

  const cancelMutation = useMutation({
    mutationFn: async (projectId: string) => {
      const response = await apiClient.post(
        `/marketing-videos/projects/${projectId}/cancel`,
      )
      return response.data as MarketingVideoProject
    },
    onSuccess: (canceled) => {
      setActiveProject(canceled)
      queryClient.invalidateQueries({ queryKey: ['storyboard-projects'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '取消渲染失败')),
  })

  const constraints: StoryboardContinuity = {
    global_constraints: parsed?.global_constraints,
    no_dialogue: parsed?.no_dialogue,
    no_subtitles: parsed?.no_subtitles,
    no_watermark: parsed?.no_watermark,
  }
  const canParse = script.trim().length > 0 && !previewMutation.isPending
  const canCreate =
    Boolean(parsed && selectedAsset && productName.trim()) &&
    Boolean(capabilities?.enabled) &&
    !createMutation.isPending

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-5"
    >
      {actionError && (
        <div className="flex items-start gap-2 border border-destructive/35 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          {actionError}
        </div>
      )}

      <section className="border border-border bg-[var(--factory-panel)]">
        <div className="grid lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="border-b border-border p-4 lg:border-b-0 lg:border-r">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <Label htmlFor="professional-script" className="text-sm font-medium">
                  专业分镜脚本文案
                </Label>
                <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                  原样保留镜头、时间码和描述；解析不调用模型，也不改写字幕内容。
                </p>
              </div>
              <span className="metric-number text-[11px] text-muted-foreground">
                {script.length}/30000
              </span>
            </div>
            <textarea
              id="professional-script"
              value={script}
              maxLength={30_000}
              onChange={(event) => {
                setScript(event.target.value)
                setParsed(null)
              }}
              placeholder={'分镜 1｜00:00–00:04｜门口的快递（时长 4 秒）\n在这里粘贴该镜头的完整画面描述...'}
              className="mt-3 min-h-[280px] w-full resize-y border border-input bg-background px-3 py-3 font-mono text-xs leading-6 outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
            />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <p className="text-[11px] leading-5 text-muted-foreground">
                解析免费；正式渲染按每个镜头实际时长扣积分
              </p>
              <Button onClick={() => previewMutation.mutate()} disabled={!canParse}>
                {previewMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <ScanLine className="mr-2 h-4 w-4" />
                )}
                {previewMutation.isPending ? '解析中...' : '解析并校验分镜'}
              </Button>
            </div>
          </div>

          <div className="space-y-4 p-4">
            <div>
              <div className="flex items-center justify-between gap-2">
                <Label>商品首帧</Label>
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span>{assets.length} 张素材</span>
                  <a href="/app/images" className="text-foreground underline underline-offset-2">
                    管理素材
                  </a>
                </div>
              </div>
              {assets.length ? (
                <div className="mt-2 grid grid-cols-5 gap-2">
                  {assets.slice(0, 5).map((asset) => (
                    <button
                      key={asset.id}
                      type="button"
                      title={asset.name}
                      aria-label={`选择 ${asset.name}`}
                      aria-pressed={selectedAssetId === asset.id}
                      onClick={() => {
                        setSelectedAssetId(asset.id)
                        if (!productName.trim()) setProductName(asset.name)
                      }}
                      className={cn(
                        'aspect-square overflow-hidden border bg-[#d9dad5]',
                        selectedAssetId === asset.id
                          ? 'border-[color:var(--factory-accent)] ring-1 ring-[color:var(--factory-accent)]'
                          : 'border-border',
                      )}
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
                  className="mt-2 flex min-h-16 items-center justify-center gap-2 border border-dashed border-border text-xs text-muted-foreground hover:text-foreground"
                >
                  <ImageIcon className="h-4 w-4" />
                  去图片工作台上传商品首帧
                </a>
              )}
              {assets.length > 0 && (
                <p className="mt-2 text-[10px] leading-4 text-muted-foreground">
                  首帧取自图片工作台的上传图或白底图，点击缩略图切换。
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="storyboard-product-name">商品名称</Label>
              <Input
                id="storyboard-product-name"
                value={productName}
                onChange={(event) => setProductName(event.target.value)}
                placeholder="用于锁定商品事实"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>目标平台</Label>
                <select
                  value={platform}
                  onChange={(event) => setPlatform(event.target.value)}
                  className="h-9 w-full border border-input bg-background px-2 text-[11px] outline-none focus:ring-2 focus:ring-ring"
                >
                  {(capabilities?.platforms || []).map((item) => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>市场</Label>
                <select
                  value={market}
                  onChange={(event) => setMarket(event.target.value)}
                  className="h-9 w-full border border-input bg-background px-2 text-[11px] outline-none focus:ring-2 focus:ring-ring"
                >
                  {['US', 'GB', 'DE', 'JP', 'SG', 'AE'].map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>模型</Label>
                <select
                  value={modelId}
                  onChange={(event) => setModelId(event.target.value)}
                  className="h-9 w-full border border-input bg-background px-2 text-[11px] outline-none focus:ring-2 focus:ring-ring"
                >
                  {(capabilities?.models || []).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.id.replace('MiniMax-', '')}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>清晰度</Label>
                <select
                  value={resolution}
                  onChange={(event) => setResolution(event.target.value)}
                  className="metric-number h-9 w-full border border-input bg-background px-2 text-[11px] outline-none focus:ring-2 focus:ring-ring"
                >
                  {(currentModel?.resolutions || ['480P']).map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </div>
            </div>

            <Button
              className="w-full"
              disabled={!canCreate}
              onClick={() => createMutation.mutate()}
            >
              {createMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <FileText className="mr-2 h-4 w-4" />
              )}
              {createMutation.isPending ? '创建中...' : '创建专业分镜项目'}
            </Button>
            {!capabilitiesQuery.isLoading && capabilities && !capabilities.enabled && (
              <p className="text-[11px] leading-5 text-[color:var(--factory-coral)]">
                视频服务尚未配置，仍可解析脚本，但暂时不能创建渲染项目。
              </p>
            )}
          </div>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_330px]">
        <section className="min-w-0 border border-border bg-[var(--factory-panel)]">
          <div className="flex min-h-[58px] flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold">分镜时间轴</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {parsed
                  ? storyboardSummary(parsed.shot_count, parsed.total_duration)
                  : '解析后逐镜头检查时间码、描述和连续性约束'}
              </p>
            </div>
            {parsed && (
              <div className="flex flex-wrap gap-1.5">
                {storyboardConstraintLabels(constraints).map((label) => (
                  <Badge key={label} variant="outline">{label}</Badge>
                ))}
              </div>
            )}
          </div>

          {parsed ? (
            <div className="space-y-4 p-4">
              {parsed.global_constraints && (
                <div className="border border-border bg-background px-3 py-2.5">
                  <p className="micro-label">全局连续性约束</p>
                  <p className="mt-2 whitespace-pre-wrap text-xs leading-6 text-muted-foreground">
                    {parsed.global_constraints}
                  </p>
                </div>
              )}
              <div className="space-y-2">
                {parsed.shots.map((shot) => (
                  <article
                    key={shot.position}
                    className="grid gap-3 border border-border bg-background px-3 py-3 sm:grid-cols-[54px_minmax(0,1fr)_auto]"
                  >
                    <div className="flex items-center gap-2 sm:block">
                      <p className="metric-number text-sm font-semibold">
                        {String(shot.position).padStart(2, '0')}
                      </p>
                      <p className="metric-number mt-1 text-[10px] text-muted-foreground">
                        {formatStoryboardTime(shot.start_seconds)}–{formatStoryboardTime(shot.end_seconds)}
                      </p>
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-medium">{shot.title}</h3>
                        <span className="text-[10px] text-muted-foreground">用户原始描述</span>
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-xs leading-6 text-muted-foreground">
                        {shot.source_text}
                      </p>
                    </div>
                    <div className="sm:text-right">
                      <p className="metric-number text-xs">{shot.duration}s</p>
                      <p className="mt-1 text-[10px] text-muted-foreground">目标时长</p>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex min-h-[420px] flex-col items-center justify-center px-6 text-center">
              <div className="flex h-14 w-14 items-center justify-center border border-border bg-secondary">
                <ScanLine className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="mt-4 text-sm font-medium">粘贴完整专业分镜脚本</p>
              <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
                支持“分镜 1｜00:00–00:04｜标题（时长 4 秒）”格式，最多 12 个镜头。
              </p>
            </div>
          )}
        </section>

        <aside className="space-y-4">
          {project && (
            <section className="border border-border bg-[var(--factory-panel)]">
              <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-semibold">{project.title}</h2>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {project.shots.length} 镜头 · {project.duration}s · {project.credits_estimated} 积分
                  </p>
                </div>
                <Badge variant={project.status === 'succeeded' ? 'secondary' : 'outline'}>
                  {projectStatusLabel(project.status)}
                </Badge>
              </div>
              <div className="space-y-3 p-4">
                <div className="max-h-56 space-y-1 overflow-y-auto">
                  {project.shots.map((shot) => (
                    <div key={shot.position} className="flex items-center justify-between gap-2 border-b border-border/60 py-1.5 text-[11px] last:border-0">
                      <span className="metric-number text-muted-foreground">
                        {String(shot.position).padStart(2, '0')} · {shot.duration}s
                      </span>
                      <span className="min-w-0 flex-1 truncate">{shot.title}</span>
                      <span className={cn(
                        shot.status === 'succeeded' && 'text-[color:var(--factory-mint)]',
                        shot.status === 'failed' && 'text-[color:var(--factory-coral)]',
                        shot.status === 'running' && 'text-[color:var(--factory-accent)]',
                      )}>
                        {shotStatusLabel(shot.status)}
                      </span>
                    </div>
                  ))}
                </div>
                {project.status === 'brief_ready' && (
                  <Button
                    className="w-full"
                    onClick={() => renderMutation.mutate(project.id)}
                    disabled={renderMutation.isPending}
                  >
                    {renderMutation.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Play className="mr-2 h-4 w-4" />
                    )}
                    {renderMutation.isPending ? '提交中...' : '确认并逐镜头生成'}
                  </Button>
                )}
                {project.status === 'rendering' && (
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => cancelMutation.mutate(project.id)}
                    disabled={cancelMutation.isPending}
                  >
                    <Square className="mr-2 h-3.5 w-3.5" />
                    取消渲染
                  </Button>
                )}
                {project.status === 'succeeded' && (
                  <MarketingVideoPreview
                    project={project}
                    voice={capabilities?.voice}
                  />
                )}
                {project.error && (
                  <p className="border border-destructive/30 bg-destructive/8 px-3 py-2 text-xs leading-5 text-destructive">
                    {project.error}
                  </p>
                )}
              </div>
            </section>
          )}

          <section className="border border-border bg-[var(--factory-panel)]">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="text-sm font-semibold">专业分镜项目</h2>
              <span className="metric-number text-[11px] text-muted-foreground">
                {history.length}
              </span>
            </div>
            <div className="max-h-[360px] overflow-y-auto p-2">
              {history.length ? (
                history.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={cn(
                      'flex w-full items-center justify-between gap-3 border-b border-border/60 px-2.5 py-2.5 text-left last:border-0',
                      item.id === selectedProjectId
                        ? 'bg-accent text-foreground'
                        : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
                    )}
                    onClick={() => {
                      setSelectedProjectId(item.id)
                      setActiveProject(item)
                    }}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-xs font-medium">{item.title}</span>
                      <span className="mt-1 block text-[11px]">
                        {item.shots.length} 镜头 · {item.duration}s
                      </span>
                    </span>
                    <span className="shrink-0 text-[10px]">{projectStatusLabel(item.status)}</span>
                  </button>
                ))
              ) : (
                <div className="px-3 py-8 text-center text-xs text-muted-foreground">
                  <Film className="mx-auto mb-2 h-5 w-5 opacity-50" />
                  暂无专业分镜项目
                </div>
              )}
            </div>
          </section>
        </aside>
      </div>
    </motion.div>
  )
}
