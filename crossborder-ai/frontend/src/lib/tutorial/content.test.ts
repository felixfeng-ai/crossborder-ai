import { describe, expect, it } from 'vitest'
import {
  TUTORIAL_QUICK_LINKS,
  TUTORIAL_SHORTCUTS,
  TUTORIAL_STEPS,
} from './content'

describe('tutorial content', () => {
  it('covers the real product workflow in order', () => {
    expect(TUTORIAL_STEPS.map((step) => step.id)).toEqual([
      'product',
      'assistant',
      'listing',
      'media',
      'publish',
      'account',
    ])
    expect(TUTORIAL_STEPS.every((step) => step.outcomes.length >= 2)).toBe(true)
    expect(
      TUTORIAL_STEPS.flatMap((step) => step.actions).every((action) =>
        action.path.startsWith('/app/'),
      ),
    ).toBe(true)
  })

  it('provides quick starts and real shortcuts', () => {
    expect(TUTORIAL_QUICK_LINKS.map((item) => item.path)).toEqual(
      expect.arrayContaining([
        '/app/products',
        '/app/agent',
        '/app/images',
        '/app/videos?tab=single',
      ]),
    )
    expect(TUTORIAL_SHORTCUTS).toContainEqual({
      keys: 'Alt + A',
      description: '在当前页面打开或关闭 AI 决策助手',
    })
  })
})
