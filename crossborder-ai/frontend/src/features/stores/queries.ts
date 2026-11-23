import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  createStoreConnectUrl,
  getCommerceStores,
  type CommerceStore,
} from './api'
import type { StoreProviderId } from './stores'

export function useCommerceStoresQuery(workspaceId: string | null) {
  return useQuery<CommerceStore[]>({
    queryKey: ['commerce-stores', workspaceId],
    enabled: Boolean(workspaceId),
    staleTime: 60_000,
    queryFn: () => getCommerceStores(workspaceId!),
  })
}

export function useConnectStoreMutation(workspaceId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { provider: StoreProviderId; shop?: string }) =>
      createStoreConnectUrl(input.provider, input.shop),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['commerce-stores', workspaceId],
      })
    },
  })
}
