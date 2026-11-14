import { Link } from 'react-router-dom'

import {
  LEGAL_CONTACT_HREF,
  LEGAL_CONTACT_EMAIL,
  PUBLIC_LEGAL_LINKS,
} from '@/lib/legalMeta'

/**
 * 公网页面共用法务页脚。
 * 单独发包给首页和法务页，保证审核入口在未登录状态也可达。
 */
export default function PublicLegalFooter() {
  return (
    <footer data-public-legal-footer className="border-t border-border bg-[var(--factory-side)]">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-7 sm:px-6 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold text-foreground">VeyaShip</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            AI 跨境决策与运营工作台
          </p>
        </div>

        <nav aria-label="公网法务导航" className="flex max-w-2xl flex-wrap gap-x-5 gap-y-2">
          {PUBLIC_LEGAL_LINKS.map((link) => (
            <Link
              key={link.path}
              to={link.path}
              className="min-h-6 text-xs leading-6 text-muted-foreground hover:text-foreground"
            >
              {link.label}
            </Link>
          ))}
          <a
            href={LEGAL_CONTACT_HREF}
            className="min-h-6 text-xs leading-6 text-muted-foreground hover:text-foreground"
            aria-label={`发送邮件至 ${LEGAL_CONTACT_EMAIL}`}
          >
            邮件联系
          </a>
        </nav>

        <p className="text-xs leading-5 text-[var(--factory-faint)]">
          © 2026 VeyaShip
        </p>
      </div>
    </footer>
  )
}
