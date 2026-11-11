export type ShopifyOrderView = 'no-channel' | 'loading' | 'error' | 'empty' | 'ready'

interface ChannelLike {
  id: string
}

interface OrderViewInput {
  selectedChannel: string | null
  isLoading: boolean
  isError: boolean
  orderCount: number
}

export function pickInitialShopifyChannelId(
  channels: ChannelLike[] | undefined,
  selectedChannel: string | null,
): string | null {
  if (selectedChannel) return selectedChannel
  return channels?.[0]?.id ?? null
}

export function resolveShopifyOrderView(
  input: OrderViewInput,
): ShopifyOrderView {
  if (!input.selectedChannel) return 'no-channel'
  if (input.isLoading) return 'loading'
  if (input.isError) return 'error'
  return input.orderCount > 0 ? 'ready' : 'empty'
}
