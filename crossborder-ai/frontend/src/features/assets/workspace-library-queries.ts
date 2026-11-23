import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { ImageCategory } from './asset-management'
import {
  deleteWorkspaceImage,
  getWorkspaceImageAssets,
  replaceWorkspaceImage,
  updateWorkspaceImageCategory,
} from './workspace-library-api'

export function useWorkspaceImageLibraryQuery(workspaceId: string | null) {
  return useQuery({
    queryKey: ['workspace-image-library', workspaceId],
    enabled: Boolean(workspaceId),
    staleTime: 15_000,
    queryFn: () => getWorkspaceImageAssets(workspaceId!),
  })
}

export function useUpdateWorkspaceImageCategoryMutation(
  workspaceId: string | null,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { assetId: string; category: ImageCategory }) =>
      updateWorkspaceImageCategory(
        workspaceId!,
        input.assetId,
        input.category,
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['workspace-image-library', workspaceId],
      })
    },
  })
}

export function useReplaceWorkspaceImageMutation(
  workspaceId: string | null,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { assetId: string; file: File }) =>
      replaceWorkspaceImage(workspaceId!, input.assetId, input.file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['workspace-image-library', workspaceId],
      })
    },
  })
}

export function useDeleteWorkspaceImageMutation(workspaceId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (assetId: string) =>
      deleteWorkspaceImage(workspaceId!, assetId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['workspace-image-library', workspaceId],
      })
    },
  })
}
