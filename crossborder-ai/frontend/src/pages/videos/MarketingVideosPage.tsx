import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useSearchParams } from 'react-router-dom'
import {
  Check,
  Captions,
  CircleAlert,
  Download,
  Film,
  Loader2,
  Mic2,
  Play,
  Sparkles,
  Square,
  WandSparkles,
} from 'lucide-react'
import apiClient from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ProductReferencePicker } from '@/components/videos/ProductReferencePicker'
import { VideoQualityControls } from '@/components/videos/VideoQualityControls'
import {
  buildMarketingPipeline,
  downloadFilename,
  estimateVoiceoverCredits,
  marketingTemplateName,
  marketingRenderProgress,
  projectStatusLabel,
  shotStatusLabel,
  totalShotDuration,
  type MarketingCapabilities,
  type MarketingVideoProject,
} from '@/lib/videos/marketing'
import {
  buildReferenceAssetsPayload,
  type ProductReferenceRole,
} from '@/lib/videos/references'
import { DEFAULT_QUALITY_TIER } from '@/lib/videos/quality'
import { toErrorMessage } from '@/utils/errorMessage'
import { cn } from '@/utils/cn'


interface SourceAsset {
  id: string
  name: string
  image_url: string
  width: number
  height: number
}

const MARKET_OPTIONS = [
  { value: 'US', label: '美国' },
  { value: 'GB', label: '英国' },
  { value: 'DE', label: '德国' },
  { value: 'JP', label: '日本' },
  { value: 'SG', label: '新加坡' },
  { value: 'AE', label: '阿联酋' },
]

const LANGUAGE_OPTIONS = [
  { value: 'en', label: '英语' },
  { value: 'de', label: '德语' },
  { value: 'ja', label: '日语' },
  { value: 'zh-CN', label: '中文' },
  { value: 'es', label: '西班牙语' },
]


export default function MarketingVideosPage({ embedded = false }: { embedded?: boolean }) {
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const projectFromQuery = searchParams.get('project') || ''
  const [selectedAssetId, setSelectedAssetId] = useState('')
  const [selectedReferenceIds, setSelectedReferenceIds] = useState<string[]>([])
  const [referenceRoles, setReferenceRoles] = useState<
    Record<string, ProductReferenceRole>
  >({})
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [activeProject, setActiveProject] = useState<MarketingVideoProject | null>(null)
  const [idea, setIdea] = useState('')
  const [productName, setProductName] = useState('')
  const [platform, setPlatform] = useState('tiktok')
  const [market, setMarket] = useState('US')
  const [language, setLanguage] = useState('en')
  const [duration, setDuration] = useState(15)
  const [templateId, setTemplateId] = useState('presenter_demo')
  const [qualityTier, setQualityTier] = useState(DEFAULT_QUALITY_TIER)
  const [stylePreset, setStylePreset] = useState('authentic_lifestyle')
  const [actionError, setActionError] = useState('')

  const capabilitiesQuery = useQuery<MarketingCapabilities>({
    queryKey: ['marketing-video-capabilities'],
    queryFn: async () => {
      const response = await apiClient.get('/marketing-videos/capabilities')
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

  const historyQuery = useQuery<MarketingVideoProject[]>({
    queryKey: ['marketing-video-projects'],
    queryFn: async () => {
      const response = await apiClient.get('/marketing-videos/projects')
      return response.data || []
    },
    refetchInterval: (query) => {
      const projects = query.state.data as MarketingVideoProject[] | undefined
      return projects?.some((project) => project.status === 'rendering') ? 3000 : false
    },
  })

  const projectQuery = useQuery<MarketingVideoProject>({
    queryKey: ['marketing-video-project', selectedProjectId],
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

  useEffect(() => {
    if (projectQuery.data) {
      setActiveProject(projectQuery.data)
      if (projectQuery.data.status === 'succeeded') {
        queryClient.invalidateQueries({ queryKey: ['marketing-video-projects'] })
      }
    }
  }, [projectQuery.data, queryClient])

  const capabilities = capabilitiesQuery.data
  const assets = assetsQuery.data || []
  const history = historyQuery.data || []
  const project = activeProject || projectQuery.data || null

  useEffect(() => {
    if (projectFromQuery && projectFromQuery !== selectedProjectId) {
      setSelectedProjectId(projectFromQuery)
    }
  }, [projectFromQuery, selectedProjectId])

  useEffect(() => {
    if (!capabilities) return
    if (!capabilities.quality_tiers.some((item) => item.id === qualityTier)) {
      setQualityTier(capabilities.quality_tiers[0]?.id || DEFAULT_QUALITY_TIER)
    }
    if (!capabilities.style_presets.some((item) => item.id === stylePreset)) {
      setStylePreset(capabilities.style_presets[0]?.id || 'authentic_lifestyle')
    }
    if (!capabilities.durations.includes(duration)) {
      setDuration(capabilities.durations[0] || 15)
    }
  }, [capabilities, duration, qualityTier, stylePreset])

  useEffect(() => {
    if (!assets.length) {
      if (selectedAssetId) setSelectedAssetId('')
      if (selectedReferenceIds.length) setSelectedReferenceIds([])
      return
    }
    const validIds = selectedReferenceIds.filter((id) =>
      assets.some((asset) => asset.id === id),
    )
    if (!validIds.length) {
      const first = assets[0].id
      setSelectedAssetId(first)
      setSelectedReferenceIds([first])
      if (!productName.trim()) setProductName(assets[0].name)
      return
    }
    if (validIds.length !== selectedReferenceIds.length) {
      setSelectedReferenceIds(validIds)
    }
    if (!validIds.includes(selectedAssetId)) {
      setSelectedAssetId(validIds[0])
    }
  }, [assets, productName, selectedAssetId, selectedReferenceIds])

  useEffect(() => {
    if (selectedProjectId || !history.length) return
    const latest = history[0]
    setSelectedProjectId(latest.id)
    setActiveProject(latest)
  }, [history, selectedProjectId])

  const selectedAsset = assets.find((asset) => asset.id === selectedAssetId) || null
  const canGeneratePlan =
    Boolean(selectedAsset) &&
    productName.trim().length > 0 &&
    idea.trim().length >= 3 &&
    capabilities?.enabled &&
    !historyQuery.isLoading

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!selectedAsset) throw new Error('请先选择商品首帧')
      const response = await apiClient.post<MarketingVideoProject>(
        '/marketing-videos/projects',
        {
          source_asset_id: selectedAsset.id,
          reference_assets: buildReferenceAssetsPayload(
            selectedAsset.id,
            selectedReferenceIds,
            referenceRoles,
          ),
          continuity_mode: 'natural',
          idea,
          product_name: productName,
          platform,
          market,
          language,
          duration,
          template_id: templateId,
          quality_tier: qualityTier,
          style_preset: stylePreset,
        },
        { headers: { 'Idempotency-Key': crypto.randomUUID() } },
      )
      return response.data
    },
    onMutate: () => setActionError(''),
    onSuccess: (created) => {
      setSelectedProjectId(created.id)
      setActiveProject(created)
      queryClient.invalidateQueries({ queryKey: ['marketing-video-projects'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '营销方案生成失败')),
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
      queryClient.invalidateQueries({ queryKey: ['marketing-video-projects'] })
      queryClient.invalidateQueries({
        queryKey: ['marketing-video-project', rendered.id],
      })
    },
    onError: (error) => setActionError(toErrorMessage(error, '营销成片生成失败')),
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
      queryClient.invalidateQueries({ queryKey: ['marketing-video-projects'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '取消营销任务失败')),
  })

  const selectProject = (next: MarketingVideoProject) => {
    setSelectedProjectId(next.id)
    setActiveProject(next)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-5"
    >
      {!embedded && (
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="page-title flex items-center gap-2">
              <Sparkles className="h-6 w-6 text-primary" />
              AI 营销视频
            </h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              输入一个营销想法，Agent 先给出钩子、脚本与多镜头分镜，确认后再生成成片。
            </p>
          </div>
          <div className="flex items-center gap-2 border border-border bg-background px-3 py-2">
            <span className="status-dot" />
            <span className="text-xs text-muted-foreground">
              {capabilities?.enabled ? '营销视频 Agent 已就绪' : '视频服务待配置'}
            </span>
          </div>
        </div>
      )}

      {actionError && (
        <div className="border border-destructive/35 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {actionError}
        </div>
      )}

      {!capabilitiesQuery.isLoading && capabilities && !capabilities.enabled && (
        <div className="flex items-start gap-3 border border-[color:var(--factory-coral)]/35 bg-[rgba(217,139,112,0.08)] px-4 py-3">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--factory-coral)]" />
          <div>
            <p className="text-sm font-medium">营销视频 Agent 暂不可用</p>
            <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
              管理员配置 MiniMax 视频服务后即可生成方案和成片。
            </p>
          </div>
        </div>
      )}

      <section className="border border-border bg-[var(--factory-panel)]">
        <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_310px]">
          <div className="border-b border-border p-4 lg:border-b-0 lg:border-r">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="marketing-idea" className="text-sm font-medium">
                想让这条广告解决什么
              </Label>
              <span className="metric-number text-[11px] text-muted-foreground">
                {idea.length}/3000
              </span>
            </div>
            <textarea
              id="marketing-idea"
              value={idea}
              maxLength={3000}
              onChange={(event) => setIdea(event.target.value)}
              placeholder="例如：面向通勤族，突出这款身体油吸收快、不沾衣服，做一个 15 秒人物演示广告"
              className="mt-2 min-h-[92px] w-full resize-y border border-input bg-background px-3 py-2.5 text-sm leading-6 outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
            />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <WandSparkles className="h-4 w-4 text-[color:var(--factory-accent)]" />
                生成方案消耗 1 积分；正式渲染前会展示镜头和总积分
              </div>
              <Button
                onClick={() => createMutation.mutate()}
                disabled={!canGeneratePlan || createMutation.isPending}
              >
                {createMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="mr-2 h-4 w-4" />
                )}
                {createMutation.isPending ? 'Agent 规划中...' : '生成创意方案'}
              </Button>
            </div>
          </div>

          <div className="p-4">
            <div className="flex items-center justify-between gap-2">
              <Label>商品主图与参考图</Label>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>{assets.length} 张素材</span>
                <a href="/app/images" className="text-foreground underline underline-offset-2">
                  管理素材
                </a>
              </div>
            </div>
            <ProductReferencePicker
              assets={assets}
              selectedIds={selectedReferenceIds}
              primaryId={selectedAssetId}
              roleByAsset={referenceRoles}
              onSelectedIdsChange={(ids) => {
                setSelectedReferenceIds(ids)
                if (!productName.trim() && ids[0]) {
                  const nextAsset = assets.find((asset) => asset.id === ids[0])
                  if (nextAsset) setProductName(nextAsset.name)
                }
              }}
              onPrimaryIdChange={setSelectedAssetId}
              onRoleChange={(assetId, role) => {
                setReferenceRoles((current) => ({ ...current, [assetId]: role }))
              }}
            />
            <p className="mt-2 text-[10px] leading-4 text-muted-foreground">
              主图控制首帧；额外参考图用于多角度商品一致性，合计最多 9 张。
            </p>
            <div className="mt-3 space-y-1.5">
              <Label htmlFor="marketing-product-name">商品名称</Label>
              <Input
                id="marketing-product-name"
                value={productName}
                onChange={(event) => setProductName(event.target.value)}
                placeholder="用于脚本与分镜"
              />
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_330px]">
        <section className="min-w-0 border border-border bg-[var(--factory-panel)]">
          <div className="flex min-h-[58px] flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold">方案与分镜</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Agent 的输出会作为后续渲染的唯一依据
              </p>
            </div>
            {project && (
              <Badge variant={project.status === 'succeeded' ? 'secondary' : 'outline'}>
                {projectStatusLabel(project.status)}
              </Badge>
            )}
          </div>

          {project ? (
            <ProjectWorkspace
              project={project}
              onRender={() => renderMutation.mutate(project.id)}
              onCancel={() => cancelMutation.mutate(project.id)}
              rendering={renderMutation.isPending}
              canceling={cancelMutation.isPending}
              voice={capabilities?.voice}
            />
          ) : (
            <div className="flex min-h-[520px] flex-col items-center justify-center px-6 text-center">
              <div className="flex h-14 w-14 items-center justify-center border border-border bg-secondary">
                <Film className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="mt-4 text-sm font-medium">先描述一个营销想法</p>
              <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
                Agent 将结合商品、平台和市场生成可审阅的多镜头方案。
              </p>
            </div>
          )}
        </section>

        <aside className="space-y-4">
          <section className="border border-border bg-[var(--factory-panel)]">
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-sm font-semibold">投放设置</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">新方案将使用以下上下文</p>
            </div>
            <div className="space-y-4 p-4">
              <div className="space-y-2">
                <Label htmlFor="marketing-platform">目标平台</Label>
                <select
                  id="marketing-platform"
                  value={platform}
                  onChange={(event) => setPlatform(event.target.value)}
                  className="h-10 w-full border border-input bg-background px-2.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                >
                  {(capabilities?.platforms || []).map((item) => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="marketing-market">市场</Label>
                  <select
                    id="marketing-market"
                    value={market}
                    onChange={(event) => setMarket(event.target.value)}
                    className="h-10 w-full border border-input bg-background px-2.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                  >
                    {MARKET_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="marketing-language">语言</Label>
                  <select
                    id="marketing-language"
                    value={language}
                    onChange={(event) => setLanguage(event.target.value)}
                    className="h-10 w-full border border-input bg-background px-2.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                  >
                    {LANGUAGE_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="space-y-2">
                <Label>成片时长</Label>
                <div className="grid grid-cols-3 gap-1 border border-border p-0.5">
                  {(capabilities?.durations || [15, 20, 30]).map((value) => (
                    <Button
                      key={value}
                      type="button"
                      variant={duration === value ? 'secondary' : 'ghost'}
                      size="sm"
                      className="metric-number h-8 text-xs"
                      onClick={() => setDuration(value)}
                    >
                      {value}s
                    </Button>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <Label>营销模板</Label>
                <div className="grid grid-cols-2 gap-1">
                  {(capabilities?.marketing_templates || []).map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={cn(
                        'min-h-10 border px-2 text-left text-[11px] leading-4 transition-colors',
                        templateId === item.id
                          ? 'border-[color:var(--factory-accent)]/70 bg-[color:var(--factory-accent)]/7'
                          : 'border-border text-muted-foreground hover:bg-accent hover:text-foreground',
                      )}
                      aria-pressed={templateId === item.id}
                      title={item.description}
                      onClick={() => setTemplateId(item.id)}
                    >
                      {item.name}
                    </button>
                  ))}
                </div>
                <p className="text-[11px] leading-5 text-muted-foreground">
                  人物模板使用 AI 品牌演示者，不作为真实消费者证言。
                </p>
              </div>
              <div className="border-t border-border pt-4">
                <VideoQualityControls
                  tiers={capabilities?.quality_tiers || []}
                  styles={capabilities?.style_presets || []}
                  qualityTier={qualityTier}
                  stylePreset={stylePreset}
                  context="marketing"
                  onQualityTierChange={setQualityTier}
                  onStylePresetChange={setStylePreset}
                />
              </div>
            </div>
          </section>

          <section className="border border-border bg-[var(--factory-panel)]">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="text-sm font-semibold">项目历史</h2>
              <span className="metric-number text-[11px] text-muted-foreground">
                {history.length}
              </span>
            </div>
            <div className="max-h-[360px] overflow-y-auto p-2">
              {history.length > 0 ? (
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
                    onClick={() => selectProject(item)}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-xs font-medium">{item.title}</span>
                      <span className="mt-1 block text-[11px]">
                        {marketingTemplateName(item.template_id)} · {item.duration}s
                      </span>
                    </span>
                    <span className="shrink-0 text-[10px]">{projectStatusLabel(item.status)}</span>
                  </button>
                ))
              ) : (
                <p className="px-3 py-8 text-center text-xs text-muted-foreground">
                  暂无营销视频项目
                </p>
              )}
            </div>
          </section>
        </aside>
      </div>
    </motion.div>
  )
}


function ProjectWorkspace({
  project,
  onRender,
  onCancel,
  rendering,
  canceling,
  voice,
}: {
  project: MarketingVideoProject
  onRender: () => void
  onCancel: () => void
  rendering: boolean
  canceling: boolean
  voice?: MarketingCapabilities['voice']
}) {
  const pipeline = buildMarketingPipeline(project)
  const plan = project.brief
  return (
    <div>
      <div className="border-b border-border px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-lg font-semibold">{project.title}</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {marketingTemplateName(project.template_id)} · {project.market} · {project.language}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="metric-number text-sm">{project.credits_estimated} 积分</span>
            {project.status === 'brief_ready' && (
              <Button onClick={onRender} disabled={rendering}>
                {rendering ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-2 h-4 w-4" />
                )}
                {rendering ? '提交中...' : '确认并生成成片'}
              </Button>
            )}
            {project.status === 'rendering' && (
              <Button variant="outline" onClick={onCancel} disabled={canceling}>
                <Square className="mr-2 h-3.5 w-3.5" />
                取消任务
              </Button>
            )}
          </div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          {pipeline.map((step, index) => (
            <div key={step.id} className="flex items-center gap-2">
              <span
                className={cn(
                  'flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[10px]',
                  step.state === 'complete' && 'border-[color:var(--factory-mint)]/50 text-[color:var(--factory-mint)]',
                  step.state === 'current' && 'border-[color:var(--factory-accent)]/60 text-[color:var(--factory-accent)]',
                  step.state === 'failed' && 'border-[color:var(--factory-coral)]/50 text-[color:var(--factory-coral)]',
                  step.state === 'pending' && 'border-border text-muted-foreground',
                )}
              >
                {step.state === 'complete' ? (
                  <Check className="h-3 w-3" />
                ) : step.state === 'failed' ? (
                  <CircleAlert className="h-3 w-3" />
                ) : (
                  index + 1
                )}
              </span>
              <span className="text-xs text-muted-foreground">{step.label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_310px]">
        <div className="space-y-5 border-b border-border p-4 lg:border-b-0 lg:border-r">
          <div>
            <p className="micro-label">开场钩子</p>
            <p className="mt-2 text-xl font-semibold leading-8">{plan.hook || 'Agent 未返回钩子'}</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="micro-label">口播脚本</p>
              <p className="mt-2 text-sm leading-6 text-[var(--factory-muted)]">
                {plan.script || '暂无脚本'}
              </p>
            </div>
            <div>
              <p className="micro-label">行动号召</p>
              <p className="mt-2 text-sm leading-6 text-[var(--factory-muted)]">
                {plan.cta || '暂无 CTA'}
              </p>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between gap-2">
              <p className="section-title text-[15px]">分镜时间线</p>
              <span className="metric-number text-[11px] text-muted-foreground">
                {totalShotDuration(project.shots)}s
              </span>
            </div>
            <div className="mt-3 space-y-2">
              {project.shots.map((shot) => (
                <div
                  key={shot.position}
                  className="grid grid-cols-[32px_minmax(0,1fr)_auto] gap-3 border border-border bg-background px-3 py-3"
                >
                  <div className="metric-number flex h-8 w-8 items-center justify-center border border-border text-xs text-muted-foreground">
                    {String(shot.position).padStart(2, '0')}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium">{shot.title}</p>
                      <span className="text-[10px] text-muted-foreground">{shot.purpose}</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
                      {shot.prompt}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="metric-number text-xs">{shot.duration}s</p>
                    <p className={cn(
                      'mt-1 text-[10px]',
                      shot.status === 'succeeded'
                        ? 'text-[color:var(--factory-mint)]'
                        : shot.status === 'failed'
                          ? 'text-[color:var(--factory-coral)]'
                          : 'text-muted-foreground',
                    )}>
                      {shotStatusLabel(shot.status)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="p-4">
          <p className="micro-label">成片预览</p>
          <div className="mt-3">
            <MarketingVideoPreview project={project} voice={voice} />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <div className="border border-border p-2.5">
              <p className="text-[10px] text-muted-foreground">镜头数</p>
              <p className="metric-number mt-1 text-lg">{project.shots.length}</p>
            </div>
            <div className="border border-border p-2.5">
              <p className="text-[10px] text-muted-foreground">预计耗时</p>
              <p className="metric-number mt-1 text-lg">{Math.max(2, project.shots.length * 2)}-{project.shots.length * 4} 分</p>
            </div>
          </div>
          {project.error && (
            <p className="mt-3 border border-destructive/30 bg-destructive/8 px-3 py-2 text-xs leading-5 text-destructive">
              {project.error}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}


export function MarketingVideoPreview({
  project,
  voice,
}: {
  project: MarketingVideoProject
  voice?: MarketingCapabilities['voice']
}) {
  const [videoUrl, setVideoUrl] = useState('')
  const [error, setError] = useState('')
  const [videoLoading, setVideoLoading] = useState(false)
  const [voiceError, setVoiceError] = useState('')
  const [voicePending, setVoicePending] = useState(false)
  const voiceCredits = estimateVoiceoverCredits(project.brief)
  const progress = marketingRenderProgress(project)

  useEffect(() => {
    setError('')
    setVideoUrl('')
    if (project.status !== 'succeeded') {
      setVideoLoading(false)
      return
    }
    if (project.video_available === false) {
      setVideoLoading(false)
      setError('成片文件缺失，请重新生成或联系管理员')
      return
    }
    const controller = new AbortController()
    let objectUrl = ''
    setVideoLoading(true)
    apiClient
      .get(`/marketing-videos/projects/${project.id}/file`, {
        responseType: 'blob',
        signal: controller.signal,
      })
      .then((response) => {
        objectUrl = URL.createObjectURL(response.data)
        setVideoUrl(objectUrl)
        setVideoLoading(false)
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(toErrorMessage(reason, '营销成片加载失败'))
          setVideoLoading(false)
        }
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [project.id, project.status, project.video_available])

  const download = async () => {
    try {
      const response = await apiClient.get(
        `/marketing-videos/projects/${project.id}/file`,
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = downloadFilename(project, 'mp4')
      link.click()
      URL.revokeObjectURL(url)
    } catch (reason) {
      setError(toErrorMessage(reason, '营销成片下载失败'))
    }
  }

  const downloadSubtitles = async () => {
    try {
      const response = await apiClient.get(
        `/marketing-videos/projects/${project.id}/subtitles`,
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = downloadFilename(project, 'srt')
      link.click()
      URL.revokeObjectURL(url)
    } catch (reason) {
      setError(toErrorMessage(reason, '字幕下载失败'))
    }
  }

  const generateVoiceover = async () => {
    setVoicePending(true)
    setVoiceError('')
    try {
      const response = await apiClient.post(
        `/marketing-videos/projects/${project.id}/voiceover`,
        null,
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = downloadFilename(project, 'mp3')
      link.click()
      URL.revokeObjectURL(url)
    } catch (reason) {
      setVoiceError(toErrorMessage(reason, '配音生成失败'))
    } finally {
      setVoicePending(false)
    }
  }

  const isVideoLoading =
    videoLoading ||
    (project.status === 'succeeded' &&
      project.video_available !== false &&
      !videoUrl &&
      !error)

  const previewContent = videoUrl ? (
    <video
      src={videoUrl}
      controls
      playsInline
      preload="metadata"
      onCanPlay={() => setVideoLoading(false)}
      onError={() => {
        setVideoLoading(false)
        setError('浏览器无法播放该成片，请下载后检查或重新生成')
      }}
      className="aspect-[9/16] max-h-[420px] w-full bg-black object-contain"
    />
  ) : error ? (
    <div className="flex min-h-52 flex-col items-center justify-center border border-destructive/30 px-4 text-center text-xs text-destructive">
      <CircleAlert className="mb-2 h-5 w-5" />
      {error}
    </div>
  ) : isVideoLoading ? (
    <div className="flex aspect-[9/16] max-h-[420px] flex-col items-center justify-center border border-border bg-[var(--factory-ground)] px-5 text-center">
      <Loader2 className="h-7 w-7 animate-spin text-[color:var(--factory-accent)]" />
      <p className="mt-3 text-xs text-muted-foreground">成片加载中</p>
      <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
        正在读取已生成的 MP4 文件
      </p>
    </div>
  ) : (
    <div className="flex aspect-[9/16] max-h-[420px] flex-col items-center justify-center border border-border bg-[var(--factory-ground)] px-5 text-center">
      {project.status === 'rendering' ? (
        <>
          <Loader2 className="h-7 w-7 animate-spin text-[color:var(--factory-accent)]" />
          <p className="mt-3 text-xs text-muted-foreground">分镜生成与合成中</p>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
            页面会自动刷新，全部镜头成功后生成成片
          </p>
        </>
      ) : project.status === 'brief_ready' ? (
        <>
          <Film className="h-7 w-7 text-muted-foreground" />
          <p className="mt-3 text-xs text-muted-foreground">确认方案后生成成片</p>
        </>
      ) : (
        <>
          <CircleAlert className="h-7 w-7 text-[color:var(--factory-coral)]" />
          <p className="mt-3 text-xs text-muted-foreground">当前没有可播放成片</p>
        </>
      )}
    </div>
  )

  return (
    <div>
      {previewContent}
      {project.status === 'rendering' && (
        <div
          className="mt-2 border border-border bg-[var(--factory-panel)] px-3 py-2.5"
          aria-label="成片生成进度"
        >
          <div className="flex items-center justify-between gap-3 text-[11px]">
            <span className="font-medium">{progress.label}</span>
            <span className="metric-number text-muted-foreground">
              {progress.percent}%
            </span>
          </div>
          <div
            className="mt-2 h-1 overflow-hidden bg-border"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress.percent}
          >
            <div
              className="h-full bg-[color:var(--factory-accent)] transition-[width] duration-500"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
          <div className="mt-2 flex items-center justify-between gap-3 text-[10px] text-muted-foreground">
            <span>{progress.detail}</span>
            <span className="metric-number shrink-0">
              {progress.completed}/{progress.total}
            </span>
          </div>
        </div>
      )}
      {project.status === 'succeeded' && (
        <div className="mt-2 space-y-2">
          <Button variant="outline" size="sm" className="w-full" onClick={download}>
            <Download className="mr-2 h-4 w-4" />
            下载 MP4
          </Button>
          {project.subtitle_url && (
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={downloadSubtitles}
            >
              <Captions className="mr-2 h-4 w-4" />
              下载 SRT 字幕
            </Button>
          )}
          {project.mode !== 'script' && !project.continuity?.no_dialogue && (
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={generateVoiceover}
              disabled={!voice?.enabled || voicePending}
              title={voice?.reason || '生成并下载 AI 配音'}
            >
              {voicePending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Mic2 className="mr-2 h-4 w-4" />
              )}
              {voicePending ? '配音生成中' : `生成 AI 配音 ${voiceCredits} 积分`}
            </Button>
          )}
          <p className="text-[10px] leading-4 text-muted-foreground">
            {project.subtitles_burned_in
              ? '字幕已烧录进成片，也可单独下载 SRT'
              : project.subtitle_url
                ? '当前成片为独立字幕版本，SRT 可单独下载'
                : project.mode === 'script'
                  ? '专业分镜不自动生成字幕，避免编造'
                  : '成片保持无字幕输出'}
          </p>
          {project.mode !== 'script' && !project.continuity?.no_dialogue && voice && !voice.enabled && (
            <p className="text-[10px] leading-4 text-[color:var(--factory-coral)]">
              {voice.reason}
            </p>
          )}
          {voiceError && (
            <p className="text-[10px] leading-4 text-destructive">{voiceError}</p>
          )}
        </div>
      )}
    </div>
  )
}
