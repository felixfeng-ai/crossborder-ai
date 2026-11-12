import { describe, expect, it } from 'vitest'
import {
  buildImageMaterials,
  buildVideoMaterials,
  formatMaterialDateTime,
} from './materials'


describe('material center normalization', () => {
  it('聚合上传、白底和 AI 图片', () => {
    const items = buildImageMaterials(
      [
        {
          id: 'upload-1',
          name: '商品原图',
          kind: 'upload',
          image_url: '/api/v1/images/assets/upload-1/file',
          width: 800,
          height: 800,
          file_size: 1200,
          created_at: '2026-11-11T10:00:00Z',
        },
        {
          id: 'white-1',
          name: '白底图',
          kind: 'processed',
          image_url: '/api/v1/images/assets/white-1/file',
          width: 1000,
          height: 1000,
          file_size: 1600,
          created_at: '2026-11-11T11:00:00Z',
        },
      ],
      [
        {
          task_id: 'ai-1',
          prompt: 'studio product photo',
          image_urls: ['https://cdn.example.com/ai.webp'],
          model_used: 'wanx',
          status: 'completed',
          created_at: '2026-11-11T12:00:00Z',
        },
      ],
    )

    expect(items).toHaveLength(3)
    expect(items[0]).toMatchObject({
      type: 'image',
      source: 'generated',
      name: 'AI 生成图',
      deleteEndpoint: '/images/history/ai-1',
      prompt: 'studio product photo',
    })
    expect(items.every((item) => item.type === 'image')).toBe(true)
  })

  it('只聚合已完成的单镜头和营销成片', () => {
    const items = buildVideoMaterials(
      [
        {
          id: 'single-1',
          status: 'succeeded',
          model: 'MiniMax-H3-Lite',
          resolution: '480P',
          duration: 4,
          ratio: '9:16',
          prompt: 'single',
          credits_cost: 10,
          thumbnail_url: '/api/v1/videos/tasks/single-1/thumbnail',
          created_at: '2026-11-11T10:00:00Z',
        },
        {
          id: 'single-running',
          status: 'running',
          model: 'MiniMax-H3-Lite',
          resolution: '480P',
          duration: 4,
          ratio: '9:16',
          prompt: 'running',
          credits_cost: 10,
          created_at: '2026-11-11T11:00:00Z',
        },
      ],
      [
        {
          id: 'marketing-1',
          title: 'Terra campaign',
          status: 'succeeded',
          duration: 15,
          template_id: 'presenter_demo',
          model: 'MiniMax-H3-Lite',
          resolution: '480P',
          thumbnail_url: '/api/v1/marketing-videos/projects/marketing-1/thumbnail',
          created_at: '2026-11-11T12:00:00Z',
        },
        {
          id: 'marketing-failed',
          title: 'Failed campaign',
          status: 'failed',
          duration: 15,
          template_id: 'presenter_demo',
          model: 'MiniMax-H3-Lite',
          resolution: '480P',
          created_at: '2026-11-11T13:00:00Z',
        },
      ],
    )

    expect(items).toHaveLength(2)
    expect(items[0]).toMatchObject({
      type: 'video',
      source: 'marketing',
      name: 'Terra campaign',
      thumbnailUrl: '/api/v1/marketing-videos/projects/marketing-1/thumbnail',
      deleteEndpoint: '/marketing-videos/projects/marketing-1',
    })
    expect(items[1]).toMatchObject({
      type: 'video',
      source: 'single',
      thumbnailUrl: '/api/v1/videos/tasks/single-1/thumbnail',
      deleteEndpoint: '/videos/tasks/single-1',
    })
  })

  it('展示到分钟的生成时间', () => {
    expect(formatMaterialDateTime('2026-11-11T10:05:00')).toBe('2026-11-11 10:05')
  })
})
