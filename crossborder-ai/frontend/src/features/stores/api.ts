import apiClient from '@/api/client'
import { MOBILE_API_BASE } from '@/features/workspace-context/workspace-api'

import type { StoreProviderId } from './stores'

export interface CommerceStore {
  channel_type: string
  channel_id: string
  name: string
  status: string
}

export async function getCommerceStores(
  workspaceId: string,
): Promise<CommerceStore[]> {
  const response = await apiClient.get<CommerceStore[]>(
    `/workspaces/${workspaceId}/commerce-stores`,
    { baseURL: MOBILE_API_BASE },
  )
  return response.data
}

export async function createStoreConnectUrl(
  provider: StoreProviderId,
  shop?: string,
): Promise<string> {
  const response =
    provider === 'shopify'
      ? await apiClient.post<{ auth_url: string }>('/shopify/connect', {
          shop,
        })
      : provider === 'amazon'
        ? await apiClient.post<{ auth_url: string }>(
            '/platforms/amazon/connect-url',
          )
        : await apiClient.post<{ auth_url: string }>(
            '/platforms/temu/connect-url',
            { region: 'global' },
          )
  return response.data.auth_url
}
