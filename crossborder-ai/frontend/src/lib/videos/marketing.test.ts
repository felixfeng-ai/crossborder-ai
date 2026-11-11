import { describe, expect, it } from 'vitest'
import {
  buildMarketingPipeline,
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
})
