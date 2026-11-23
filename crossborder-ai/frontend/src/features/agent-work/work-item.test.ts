import { describe, expect, it } from 'vitest'

import {
  buildWorkItemCommand,
  primaryWorkItemAction,
  workItemNeedsAttention,
  workItemStatusMeta,
} from './work-item'
import type { WorkItemDetail } from './types'

function workItem(overrides: Partial<WorkItemDetail> = {}): WorkItemDetail {
  return {
    id: 'work-item-1',
    version: 7,
    kind: 'customer_reply',
    title: '回复买家物流问题',
    summary: '买家询问物流进度',
    status: 'awaiting_confirmation',
    priority: 'attention',
    current_step: '等待确认',
    requires_action: 'confirm',
    available_actions: [
      {
        id: 'confirm-reply',
        kind: 'confirm',
        label: '确认发送',
        risk: 'medium',
        expires_at: null,
      },
    ],
    action_runs: [],
    action_preview: null,
    result: null,
    customer_context: null,
    media_result: null,
    due_at: null,
    expires_at: null,
    created_at: '2026-11-23T00:00:00Z',
    updated_at: '2026-11-23T00:00:00Z',
    ...overrides,
  }
}

describe('agent work item behavior', () => {
  it('把跨端任务状态映射为一致的文案和风险等级', () => {
    expect(workItemStatusMeta('awaiting_confirmation')).toMatchObject({
      label: '等待你确认',
      tone: 'warning',
    })
    expect(workItemStatusMeta('retryable_failed')).toMatchObject({
      label: '执行失败，可重试',
      tone: 'danger',
    })
    expect(workItemStatusMeta('succeeded')).toMatchObject({
      label: '已完成',
      tone: 'success',
    })
  })

  it('优先选择需要人工处理的可用动作', () => {
    expect(primaryWorkItemAction(workItem())?.id).toBe('confirm-reply')
    expect(
      primaryWorkItemAction(
        workItem({
          available_actions: [
            {
              id: 'open',
              kind: 'choose',
              label: '打开',
              risk: 'low',
              expires_at: null,
            },
            {
              id: 'retry',
              kind: 'retry',
              label: '重试',
              risk: 'medium',
              expires_at: null,
            },
          ],
        }),
      )?.id,
    ).toBe('retry')
    expect(primaryWorkItemAction(workItem({ available_actions: [] }))).toBeNull()
  })

  it('确认命令携带工作项版本和幂等键', () => {
    expect(
      buildWorkItemCommand(workItem(), {
        actionId: 'confirm-reply',
        action: 'confirm',
        idempotencyKey: 'idem-1',
        payload: { language: 'en' },
      }),
    ).toEqual({
      action: 'confirm',
      action_id: 'confirm-reply',
      expected_version: 7,
      payload: { language: 'en' },
      idempotency_key: 'idem-1',
    })
  })

  it('只把未完成且要求动作的任务标为需要注意', () => {
    expect(workItemNeedsAttention(workItem())).toBe(true)
    expect(
      workItemNeedsAttention(workItem({ requires_action: 'none' })),
    ).toBe(false)
    expect(workItemNeedsAttention(workItem({ status: 'succeeded' }))).toBe(false)
  })
})
