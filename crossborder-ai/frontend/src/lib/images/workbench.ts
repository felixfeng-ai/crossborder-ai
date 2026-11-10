export interface WorkbenchAsset {
  id: string
  name: string
  kind: 'upload' | 'processed'
  image_url: string
  width: number
  height: number
  file_size: number
  preset_id?: string | null
  platform?: string | null
  background_mode?: string | null
  created_at: string
}

export interface GeneratedImageHistory {
  task_id: string
  prompt: string
  image_urls: string[]
  model_used: string
  status: string
  created_at: string
}

export interface WorkbenchLibraryItem {
  id: string
  name: string
  kind: 'upload' | 'processed' | 'generated'
  image_url: string
  width: number | null
  height: number | null
  file_size: number | null
  platform?: string | null
  created_at: string
}

export function buildLibraryItems(
  assets: WorkbenchAsset[],
  history: GeneratedImageHistory[],
): WorkbenchLibraryItem[] {
  const localItems: WorkbenchLibraryItem[] = assets.map((asset) => ({
    id: asset.id,
    name: asset.name,
    kind: asset.kind,
    image_url: asset.image_url,
    width: asset.width,
    height: asset.height,
    file_size: asset.file_size,
    platform: asset.platform,
    created_at: asset.created_at,
  }))

  const generatedItems: WorkbenchLibraryItem[] = history.flatMap((task) =>
    (task.image_urls || []).map((url, index) => ({
      id: `${task.task_id}-${index}`,
      name: `AI 生成 · ${task.prompt}`,
      kind: 'generated' as const,
      image_url: url,
      width: null,
      height: null,
      file_size: null,
      platform: 'AI',
      created_at: task.created_at,
    })),
  )

  return [...localItems, ...generatedItems].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || Number.isNaN(bytes)) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
