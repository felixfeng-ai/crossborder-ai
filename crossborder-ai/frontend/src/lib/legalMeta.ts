/**
 * 公网法务元数据。
 * 与完整法务正文分离，避免首页页脚把多篇长文档打进首屏共享包。
 */
export const LEGAL_CONTACT_EMAIL = 'admin@veyaship.com'
export const LEGAL_CONTACT_HREF = `mailto:${LEGAL_CONTACT_EMAIL}`
export const LEGAL_OPERATOR_NAME = '冯斯远'
export const LEGAL_OPERATOR_DISCLOSURE =
  `VeyaShip 由${LEGAL_OPERATOR_NAME}以个人经营者身份运营。`

export const PUBLIC_LEGAL_LINKS = [
  { path: '/terms', label: '服务条款' },
  { path: '/privacy', label: '隐私政策' },
  { path: '/data-processing', label: '数据处理' },
  { path: '/ai-disclosure', label: 'AI 使用说明' },
  { path: '/security', label: '安全说明' },
  { path: '/report', label: '侵权举报' },
  { path: '/contact', label: '联系我们' },
] as const
