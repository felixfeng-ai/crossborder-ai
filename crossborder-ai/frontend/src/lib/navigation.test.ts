import { describe, expect, it } from 'vitest'
import {
  NAVIGATION_GROUPS,
  getHeaderContext,
  videoTabFromSearch,
} from './navigation'


describe('navigation architecture', () => {
  it('按工作流分组并只保留一个视频入口', () => {
    expect(NAVIGATION_GROUPS.map((group) => group.label)).toEqual([
      '经营',
      'AI 创作',
      '运营',
      '账户',
    ])
    const paths = NAVIGATION_GROUPS.flatMap((group) =>
      group.items.map((item) => item.path),
    )
    expect(paths.filter((path) => path === '/app/videos')).toHaveLength(1)
    expect(paths).not.toContain('/app/marketing-videos')
    expect(paths).not.toContain('/app/batch')
    expect(paths).not.toContain('/app/content')
  })

  it('为顶部栏提供页面上下文', () => {
    expect(getHeaderContext('/app/assets')).toMatchObject({
      group: 'AI 创作',
      title: '素材中心',
    })
    expect(getHeaderContext('/app/content')).toMatchObject({
      group: 'Listing 中心',
      title: 'AI Listing',
    })
    expect(getHeaderContext('/app/videos')).toMatchObject({
      group: 'AI 创作',
      title: '视频工作台',
    })
  })

  it('解析视频 Tab 查询参数', () => {
    expect(videoTabFromSearch('?tab=single')).toBe('single')
    expect(videoTabFromSearch('?tab=marketing')).toBe('marketing')
    expect(videoTabFromSearch('?tab=unknown')).toBe('marketing')
    expect(videoTabFromSearch('')).toBe('marketing')
  })
})
