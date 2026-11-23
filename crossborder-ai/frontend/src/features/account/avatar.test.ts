import { describe, expect, it } from 'vitest'

import { avatarInitial } from './avatar'

describe('account avatar', () => {
  it('使用姓名或邮箱首字符作为无头像回退', () => {
    expect(avatarInitial('Felix')).toBe('F')
    expect(avatarInitial('  小Veya')).toBe('小')
    expect(avatarInitial('drir@example.com')).toBe('D')
    expect(avatarInitial('   ')).toBe('U')
    expect(avatarInitial(null)).toBe('U')
  })
})
