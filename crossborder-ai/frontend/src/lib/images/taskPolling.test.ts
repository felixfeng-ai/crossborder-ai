import { describe, expect, it } from 'vitest'

import {
  ImageTaskTimeoutError,
  waitForImageTask,
  type ImageTaskStatus,
} from './taskPolling'

const completed: ImageTaskStatus = {
  task_id: 'task-1',
  status: 'completed',
  image_urls: ['https://img.example.com/1.jpg'],
}

describe('waitForImageTask', () => {
  it('持续轮询直到 completed', async () => {
    const responses: ImageTaskStatus[] = [
      { task_id: 'task-1', status: 'processing', image_urls: [] },
      completed,
    ]
    const result = await waitForImageTask(
      'task-1',
      async () => responses.shift()!,
      { sleep: async () => undefined },
    )
    expect(result.image_urls).toEqual(['https://img.example.com/1.jpg'])
  })

  it('failed 状态抛中文错误', async () => {
    await expect(
      waitForImageTask(
        'task-1',
        async () => ({
          task_id: 'task-1',
          status: 'failed',
          image_urls: [],
          error: '图片服务余额不足',
        }),
        { sleep: async () => undefined },
      ),
    ).rejects.toThrow('图片服务余额不足')
  })

  it('超过截止时间抛超时错误', async () => {
    let current = 0
    await expect(
      waitForImageTask(
        'task-1',
        async () => ({ task_id: 'task-1', status: 'processing', image_urls: [] }),
        {
          timeoutMs: 100,
          intervalMs: 50,
          now: () => current,
          sleep: async () => { current += 50 },
        },
      ),
    ).rejects.toBeInstanceOf(ImageTaskTimeoutError)
  })
})
