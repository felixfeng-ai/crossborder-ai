export interface ImageAssetInput {
  id: string
  name: string
  kind: 'upload' | 'processed' | 'generated'
  image_url: string
  width: number
  height: number
  file_size: number
  platform?: string | null
  generation_task_id?: string | null
  variant_index?: number | null
  created_at: string
}

export interface GeneratedImageHistoryInput {
  task_id: string
  prompt: string
  image_urls: string[]
  model_used: string
  status: string
  created_at: string
}

export interface VideoTaskInput {
  id: string
  status: string
  model: string
  resolution: string
  duration: number
  ratio: string
  prompt: string
  credits_cost: number
  thumbnail_url?: string | null
  created_at: string
}

export interface MarketingProjectInput {
  id: string
  title: string
  status: string
  duration: number
  template_id: string
  model: string
  resolution: string
  thumbnail_url?: string | null
  created_at: string
}

export interface ImageMaterial {
  id: string
  type: 'image'
  source: 'upload' | 'processed' | 'generated'
  name: string
  url: string
  createdAt: string
  width?: number
  height?: number
  prompt?: string
  model?: string
  fileSize?: number
  platform?: string | null
  deleteEndpoint: string
}

export interface VideoMaterial {
  id: string
  type: 'video'
  source: 'single' | 'marketing'
  name: string
  createdAt: string
  duration: number
  model: string
  resolution: string
  thumbnailUrl?: string | null
  fileEndpoint: string
  deleteEndpoint: string
}

const IMAGE_SOURCE_LABELS: Record<ImageMaterial['source'], string> = {
  upload: '上传原图',
  processed: '白底图',
  generated: 'AI 生成图',
}

export function imageSourceLabel(source: ImageMaterial['source']): string {
  return IMAGE_SOURCE_LABELS[source]
}

export function buildImageMaterials(
  assets: ImageAssetInput[],
  history: GeneratedImageHistoryInput[],
): ImageMaterial[] {
  const local: ImageMaterial[] = assets.map((asset) => ({
    id: asset.id,
    type: 'image',
    source: asset.kind,
    name: asset.name,
    url: asset.image_url,
    createdAt: asset.created_at,
    width: asset.width,
    height: asset.height,
    fileSize: asset.file_size,
    platform: asset.platform,
    deleteEndpoint: `/images/assets/${asset.id}`,
  }))
  const materializedVariants = new Set(
    assets
      .filter((asset) => asset.generation_task_id && asset.variant_index != null)
      .map((asset) => `${asset.generation_task_id}-${asset.variant_index}`),
  )
  const generated: ImageMaterial[] = history.flatMap((task) =>
    (task.image_urls || []).flatMap((url, index) => {
      if (materializedVariants.has(`${task.task_id}-${index}`)) return []
      return [{
        id: `${task.task_id}-${index}`,
        type: 'image' as const,
        source: 'generated' as const,
        name: 'AI 生成图',
        url,
        createdAt: task.created_at,
        prompt: task.prompt,
        model: task.model_used,
        deleteEndpoint: `/images/history/${task.task_id}`,
      }]
    }),
  )
  return [...local, ...generated].sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  )
}

export function buildVideoMaterials(
  singleClips: VideoTaskInput[],
  marketingProjects: MarketingProjectInput[],
): VideoMaterial[] {
  const single: VideoMaterial[] = singleClips
    .filter((task) => task.status === 'succeeded')
    .map((task) => ({
      id: task.id,
      type: 'video',
      source: 'single',
      name: `单镜头 · ${task.model}`,
      createdAt: task.created_at,
      duration: task.duration,
      model: task.model,
      resolution: task.resolution,
      thumbnailUrl: task.thumbnail_url || null,
      fileEndpoint: `/videos/tasks/${task.id}/file`,
      deleteEndpoint: `/videos/tasks/${task.id}`,
    }))
  const marketing: VideoMaterial[] = marketingProjects
    .filter((project) => project.status === 'succeeded')
    .map((project) => ({
      id: project.id,
      type: 'video',
      source: 'marketing',
      name: project.title,
      createdAt: project.created_at,
      duration: project.duration,
      model: project.model,
      resolution: project.resolution,
      thumbnailUrl: project.thumbnail_url || null,
      fileEndpoint: `/marketing-videos/projects/${project.id}/file`,
      deleteEndpoint: `/marketing-videos/projects/${project.id}`,
    }))
  return [...marketing, ...single].sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  )
}

export function formatMaterialDateTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const pad = (part: number) => String(part).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}
