import { QueryClient } from '@tanstack/react-query'

export function shouldRetryQuery(
  failureCount: number,
  error: unknown,
): boolean {
  const status = (error as { response?: { status?: number } }).response?.status
  if (status && status >= 400 && status < 500) return false
  return failureCount < 2
}

export function retryDelay(attemptIndex: number): number {
  return Math.min(1_000 * 2 ** attemptIndex, 8_000)
}

/**
 * 全应用共享同一个 QueryClient，登录态切换时由认证层统一清空，
 * 防止上一个账号的工作区、任务和店铺缓存串入新会话。
 */
export const appQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 4xx 不重试；网络抖动和服务端 5xx 使用有限指数退避。
      retry: shouldRetryQuery,
      retryDelay,
      refetchOnReconnect: true,
      refetchOnWindowFocus: false,
      staleTime: 5 * 60 * 1000,
    },
  },
})
