import { describe, expect, it } from 'vitest'

import { buildLibraryItems, formatFileSize } from './workbench'

describe('image workbench helpers', () => {
  it('合并上传素材、处理后素材和 AI 生成历史', () => {
    const items = buildLibraryItems(
      [
        {
          id: 'asset-upload',
          name: '原图',
          kind: 'upload',
          image_url: '/api/v1/images/assets/asset-upload/file',
          width: 1200,
          height: 1200,
          file_size: 120000,
          created_at: '2026-11-11T01:00:00Z',
        },
        {
          id: 'asset-processed',
          name: 'Amazon 白底图',
          kind: 'processed',
          image_url: '/api/v1/images/assets/asset-processed/file',
          width: 2000,
          height: 2000,
          file_size: 220000,
          preset_id: 'amazon-main',
          platform: 'Amazon',
          created_at: '2026-11-11T02:00:00Z',
        },
      ],
      [
        {
          task_id: 'task-1',
          prompt: 'product photo',
          image_urls: ['https://example.com/generated.jpg'],
          model_used: 'wanx',
          status: 'completed',
          created_at: '2026-11-11T03:00:00Z',
        },
      ],
    )

    expect(items).toHaveLength(3)
    expect(items.map((item) => item.kind)).toEqual([
      'generated',
      'processed',
      'upload',
    ])
    expect(items[0].name).toContain('AI 生成')
    expect(items[0]).toMatchObject({
      taskId: 'task-1',
      prompt: 'product photo',
      model: 'wanx',
    })
  })

  it('格式化素材文件大小', () => {
    expect(formatFileSize(800)).toBe('800 B')
    expect(formatFileSize(1536)).toBe('1.5 KB')
    expect(formatFileSize(2 * 1024 * 1024)).toBe('2.0 MB')
  })

  it('已入库的生成图不再重复展示远端历史结果', () => {
    const items = buildLibraryItems(
      [
        {
          id: 'generated-asset',
          name: 'AI 生成 · product photo',
          kind: 'generated',
          image_url: '/api/v1/images/assets/generated-asset/file',
          width: 1024,
          height: 1024,
          file_size: 180000,
          generation_task_id: 'task-1',
          variant_index: 0,
          created_at: '2026-11-11T03:00:00Z',
        },
      ],
      [
        {
          task_id: 'task-1',
          prompt: 'product photo',
          image_urls: ['https://example.com/generated.jpg'],
          model_used: 'wanx',
          status: 'completed',
          created_at: '2026-11-11T03:00:00Z',
        },
      ],
    )

    expect(items).toHaveLength(1)
    expect(items[0].id).toBe('generated-asset')
  })
})
