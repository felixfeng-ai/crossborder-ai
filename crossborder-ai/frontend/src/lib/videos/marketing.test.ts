import { describe, expect, it } from 'vitest'
import {
  buildMarketingPipeline,
  downloadFilename,
  estimateVoiceoverCredits,
  marketingRenderProgress,
  marketingTemplateName,
  projectStatusLabel,
  shotStatusLabel,
  totalShotDuration,
  type MarketingVideoProject,
  type MarketingVideoShot,
} from './marketing'


const shots: MarketingVideoShot[] = [
  { position: 1, title: 'Hook', purpose: 'hook', prompt: 'hook', duration: 5, status: 'planned' },
  { position: 2, title: 'Demo', purpose: 'presenter', prompt: 'demo', duration: 5, status: 'planned' },
  { position: 3, title: 'CTA', purpose: 'cta', prompt: 'cta', duration: 5, status: 'planned' },
]

const project: MarketingVideoProject = {
  id: 'project-1',
  title: 'Terra campaign',
  product_name: 'Terra',
  idea: 'show the product',
  platform: 'tiktok',
  market: 'US',
  language: 'en',
  duration: 15,
  template_id: 'presenter_demo',
  model: 'MiniMax-H3-Lite',
  resolution: '480P',
  status: 'brief_ready',
  brief: { hook: 'Meet Terra', cta: 'Shop now' },
  shots,
  credits_estimated: 30,
  credits_charged: 0,
  created_at: '2026-11-11T00:00:00Z',
}


describe('marketing video helpers', () => {
  it('展示中文项目与分镜状态', () => {
    expect(projectStatusLabel('brief_ready')).toBe('待审阅')
    expect(projectStatusLabel('rendering')).toBe('生成中')
    expect(shotStatusLabel('running')).toBe('生成中')
    expect(marketingTemplateName('presenter_demo')).toBe('人物演示')
  })

  it('计算分镜总时长与审批流水线', () => {
    expect(totalShotDuration(shots)).toBe(15)
    const pipeline = buildMarketingPipeline(project)
    expect(pipeline.map((step) => step.label)).toEqual([
      '营销方案',
      '分镜生成',
      '成片合成',
    ])
    expect(pipeline[0].state).toBe('current')
    expect(pipeline[1].state).toBe('pending')
  })

  it('使用商品和平台生成可读下载文件名', () => {
    expect(downloadFilename(project, 'srt')).toBe(
      'Terra-tiktok-营销成片字幕.srt',
    )
    expect(
      downloadFilename(
        {
          ...project,
          product_name: 'DONMIS / 圣诞:礼盒',
        },
        'mp4',
      ),
    ).toBe(
      'DONMIS-圣诞-礼盒-tiktok-营销成片.mp4',
    )
  })

  it('按已完成镜头计算生成进度', () => {
    const renderingProject: MarketingVideoProject = {
      ...project,
      status: 'rendering',
      shots: [
        { ...shots[0], status: 'succeeded' },
        { ...shots[1], status: 'running' },
        { ...shots[2], status: 'planned' },
      ],
    }

    expect(marketingRenderProgress(renderingProject)).toMatchObject({
      completed: 1,
      total: 3,
      percent: 29,
      label: '分镜生成中',
    })

    const assemblingProject: MarketingVideoProject = {
      ...renderingProject,
      shots: renderingProject.shots.map((shot) => ({
        ...shot,
        status: 'succeeded',
      })),
    }
    expect(marketingRenderProgress(assemblingProject)).toMatchObject({
      completed: 3,
      total: 3,
      percent: 94,
      label: '正在合成成片',
    })
  })

  it('按配音字符数计算最低积分', () => {
    expect(estimateVoiceoverCredits({ hook: 'Hi', cta: 'Shop now' })).toBe(3)
    expect(
      estimateVoiceoverCredits({
        script: 'x'.repeat(260),
      }),
    ).toBe(3)
    expect(
      estimateVoiceoverCredits({
        script: 'x'.repeat(340),
      }),
    ).toBe(4)
  })
})
