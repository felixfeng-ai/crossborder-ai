import { describe, expect, it } from 'vitest'
import {
  buildAgentContextLabels,
  buildSidecarIntro,
  buildSidecarPlaceholder,
  buildSidecarQuickActions,
  deriveAgentPageContext,
  isAgentFullPage,
  normalizeAgentPageContext,
} from './sidecar'

describe('agent sidecar context', () => {
  it('hides the launcher on full agent pages', () => {
    expect(isAgentFullPage('/app/agent')).toBe(true)
    expect(isAgentFullPage('/app/marketing-agent')).toBe(true)
    expect(isAgentFullPage('/app/images')).toBe(false)
  })

  it('derives a useful context for image and video workbenches', () => {
    expect(deriveAgentPageContext('/app/images')).toMatchObject({
      route: '/app/images',
      page: '图片工作台',
    })
    expect(deriveAgentPageContext('/app/videos')).toMatchObject({
      route: '/app/videos',
      page: '视频工作台',
    })
  })

  it('removes empty and duplicate details before sending context to the agent', () => {
    const context = normalizeAgentPageContext({
      route: '/app/videos',
      page: '视频工作台',
      details: [
        '商品图生视频',
        ' 商品图生视频 ',
        '',
        '当前首帧',
        '高端静奢',
        '第三项',
        '第四项',
        '第五项',
        '第六项',
      ],
      video_tab: 'single',
    })

    expect(context.details).toEqual([
      '商品图生视频',
      '当前首帧',
      '高端静奢',
      '第三项',
      '第四项',
      '第五项',
    ])
    expect(context.video_tab).toBe('single')
  })

  it('builds compact labels without repeating the page title', () => {
    const labels = buildAgentContextLabels({
      route: '/app/images',
      page: '图片工作台',
      details: ['图片工作台', '商品 TERRA', 'Amazon 主图'],
    })

    expect(labels).toEqual(['图片工作台', '商品 TERRA', 'Amazon 主图'])
  })

  it('adapts the sidecar intro and actions to the current workbench', () => {
    const imageContext = {
      route: '/app/images',
      page: '图片工作台',
      details: ['当前素材：TERRA 商品原图', '平台预设：Amazon 主图'],
    }
    const videoContext = {
      route: '/app/videos',
      page: '视频工作台',
      details: ['商品图生视频'],
      video_tab: 'single',
    }

    expect(buildSidecarIntro(imageContext)).toContain('当前图片')
    expect(buildSidecarQuickActions(imageContext).map((item) => item.label))
      .toEqual(['分析当前图片', '检查主图合规', '白底图建议', '继续做视频'])
    expect(buildSidecarIntro(videoContext)).toContain('当前视频')
    expect(buildSidecarQuickActions(videoContext).map((item) => item.label))
      .toEqual(['优化镜头提示', '检查首帧', '估算积分', '查看素材'])
    expect(buildSidecarPlaceholder(imageContext)).toContain('当前图片')
    expect(buildSidecarPlaceholder(videoContext)).toContain('当前视频')
  })
})
