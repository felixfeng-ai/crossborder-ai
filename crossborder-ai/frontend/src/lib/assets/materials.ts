export interface ImageAssetInput {
  id: string
  name: string
  kind: 'upload' | 'processed'
  image_url: string
  width: number
  height: number
  file_size: number
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
  fileEndpoint: string
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
  }))
  const generated: ImageMaterial[] = history.flatMap((task) =>
    (task.image_urls || []).map((url, index) => ({
      id: `${task.task_id}-${index}`,
      type: 'image' as const,
      source: 'generated' as const,
      name: 'AI 生成图',
      url,
      createdAt: task.created_at,
      prompt: task.prompt,
      model: task.model_used,
    })),
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
      fileEndpoint: `/videos/tasks/${task.id}/file`,
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
      fileEndpoint: `/marketing-videos/projects/${project.id}/file`,
    }))
  return [...marketing, ...single].sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  )
}
