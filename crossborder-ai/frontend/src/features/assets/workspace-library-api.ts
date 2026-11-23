import apiClient from '@/api/client'
import { MOBILE_API_BASE } from '@/features/workspace-context/workspace-api'

import type { ImageCategory } from './asset-management'

export interface WorkspaceImageAsset {
  id: string
  name: string
  url: string
  content_type: string
  width: number
  height: number
  file_size: number
  sort_order: number
  category: ImageCategory
  created_at: string
  updated_at: string
}

export async function getWorkspaceImageAssets(
  workspaceId: string,
): Promise<WorkspaceImageAsset[]> {
  const response = await apiClient.get<WorkspaceImageAsset[]>(
    `/workspaces/${workspaceId}/assets/images`,
    { baseURL: MOBILE_API_BASE },
  )
  return response.data
}

export async function updateWorkspaceImageCategory(
  workspaceId: string,
  assetId: string,
  category: ImageCategory,
): Promise<WorkspaceImageAsset> {
  const response = await apiClient.patch<WorkspaceImageAsset>(
    `/workspaces/${workspaceId}/assets/images/${assetId}/category`,
    { category },
    { baseURL: MOBILE_API_BASE },
  )
  return response.data
}

export async function replaceWorkspaceImage(
  workspaceId: string,
  assetId: string,
  file: File,
): Promise<WorkspaceImageAsset> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiClient.post<WorkspaceImageAsset>(
    `/workspaces/${workspaceId}/assets/images/${assetId}/replace`,
    form,
    { baseURL: MOBILE_API_BASE },
  )
  return response.data
}

export async function deleteWorkspaceImage(
  workspaceId: string,
  assetId: string,
): Promise<void> {
  await apiClient.delete(
    `/workspaces/${workspaceId}/assets/images/${assetId}`,
    { baseURL: MOBILE_API_BASE },
  )
}
