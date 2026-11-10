export interface ImageTaskStatus {
  task_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed' | string
  image_urls: string[]
  model_used?: string
  error?: string | null
}

export class ImageTaskTimeoutError extends Error {
  constructor(message = '图片生成超时，请稍后到图片历史查看') {
    super(message)
    this.name = 'ImageTaskTimeoutError'
  }
}

interface WaitOptions {
  timeoutMs?: number
  intervalMs?: number
  sleep?: (ms: number) => Promise<void>
  now?: () => number
}

/**
 * 轮询图片任务直到终态。
 *
 * 这里把 sleep/now 做成可注入参数，便于单测覆盖完成、失败和超时，
 * 也避免前端组件测试依赖真实计时器。
 */
export async function waitForImageTask(
  taskId: string,
  fetchStatus: (taskId: string) => Promise<ImageTaskStatus>,
  options: WaitOptions = {},
): Promise<ImageTaskStatus> {
  const timeoutMs = options.timeoutMs ?? 120000
  const intervalMs = options.intervalMs ?? 1500
  const sleep = options.sleep ?? ((ms: number) => new Promise((resolve) => setTimeout(resolve, ms)))
  const now = options.now ?? (() => Date.now())
  const deadline = now() + timeoutMs

  while (now() < deadline) {
    const task = await fetchStatus(taskId)
    if (task.status === 'completed') return task
    if (task.status === 'failed') {
      throw new Error(task.error || '图片生成失败，请稍后重试')
    }
    await sleep(intervalMs)
  }

  throw new ImageTaskTimeoutError()
}
