import { useEffect } from 'react'
import { ArrowLeft, Mail } from 'lucide-react'
import { Link } from 'react-router-dom'

import { BrandMark } from '@/components/brand/BrandMark'
import PublicLegalFooter from '@/components/legal/PublicLegalFooter'
import {
  LEGAL_DOCUMENTS,
} from '@/lib/legal'
import { LEGAL_CONTACT_EMAIL, LEGAL_CONTACT_HREF } from '@/lib/legalMeta'

type LegalPageProps = {
  path: string
}

function formatLegalDate(value: string): string {
  const [year, month, day] = value.split('-')
  return `${year}年${Number(month)}月${Number(day)}日`
}

/**
 * 公网法务文档页。
 * 正文是页面主角；桌面目录只做定位，移动端改为单列，避免长文档在窄屏被切碎。
 */
export default function LegalPage({ path }: LegalPageProps) {
  const legalDocument = LEGAL_DOCUMENTS.find((item) => item.path === path)

  useEffect(() => {
    const previousTitle = window.document.title
    window.document.title = legalDocument
      ? `${legalDocument.title} | VeyaShip`
      : '文档不存在 | VeyaShip'
    return () => {
      window.document.title = previousTitle
    }
  }, [legalDocument])

  if (!legalDocument) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-[var(--factory-ground)] px-4 text-sm text-muted-foreground">
        未找到对应文档
      </div>
    )
  }

  return (
    <div
      data-legal-document={legalDocument.slug}
      className="min-h-[100dvh] bg-[var(--factory-ground)] text-foreground"
    >
      <header className="border-b border-border bg-[var(--factory-side)]">
        <div className="mx-auto flex min-h-16 w-full max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/" className="flex min-w-0 items-center gap-2.5" aria-label="返回 VeyaShip 首页">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[5px] border border-[var(--factory-line-strong)] bg-[var(--factory-panel)]">
              <BrandMark className="h-5 w-5" />
            </span>
            <span className="min-w-0">
              <span className="block font-latin text-sm font-semibold leading-5">VeyaShip</span>
              <span className="block truncate text-[11px] leading-4 text-muted-foreground">
                公开法务与合规中心
              </span>
            </span>
          </Link>
          <Link
            to="/"
            className="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-[5px] border border-[var(--factory-line-strong)] px-3 text-xs text-muted-foreground hover:border-[var(--factory-accent)] hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            返回首页
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-4 pb-20 pt-12 sm:px-6 lg:pt-16">
        <div className="max-w-3xl">
          <p className="font-mono text-xs text-[var(--factory-accent)]">
            VERSION {legalDocument.version}
          </p>
          <h1 className="mt-4 text-[32px] font-semibold leading-[1.25] sm:text-[40px]">
            {legalDocument.title}
          </h1>
          <p className="mt-4 max-w-[68ch] text-sm leading-7 text-muted-foreground sm:text-[15px]">
            {legalDocument.summary}
          </p>
          <dl className="mt-6 flex flex-wrap gap-x-8 gap-y-2 border-t border-border pt-4 text-xs leading-5">
            <div className="flex gap-2">
              <dt className="text-[var(--factory-faint)]">生效日期</dt>
              <dd className="text-muted-foreground">{formatLegalDate(legalDocument.effectiveDate)}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-[var(--factory-faint)]">版本</dt>
              <dd className="text-muted-foreground">{legalDocument.version}</dd>
            </div>
          </dl>
        </div>

        <div className="mt-10 grid gap-10 border-t border-border pt-8 lg:grid-cols-[220px_minmax(0,760px)] lg:gap-16">
          <nav aria-label="法务目录" className="lg:sticky lg:top-6 lg:self-start">
            <p className="text-xs font-medium text-foreground">本页目录</p>
            <ol className="mt-3 space-y-1 border-l border-border">
              {legalDocument.sections.map((section) => (
                <li key={section.id}>
                  <a
                    href={`#section-${section.id}`}
                    className="block min-h-8 border-l border-transparent py-1 pl-3 text-xs leading-6 text-muted-foreground hover:border-[var(--factory-accent)] hover:text-foreground"
                  >
                    {section.title}
                  </a>
                </li>
              ))}
            </ol>
          </nav>

          <article className="min-w-0">
            <div className="space-y-10">
              {legalDocument.sections.map((section) => (
                <section
                  key={section.id}
                  id={`section-${section.id}`}
                  className="scroll-mt-6"
                >
                  <h2 className="text-lg font-semibold leading-7">{section.title}</h2>
                  <div className="mt-3 space-y-3">
                    {section.paragraphs.map((paragraph) => (
                      <p
                        key={paragraph}
                        className="text-sm leading-7 text-[var(--factory-muted)] sm:text-[15px] sm:leading-8"
                      >
                        {paragraph}
                      </p>
                    ))}
                  </div>
                  {section.bullets && section.bullets.length > 0 && (
                    <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-7 text-[var(--factory-muted)] marker:text-[var(--factory-accent)] sm:text-[15px] sm:leading-8">
                      {section.bullets.map((bullet) => (
                        <li key={bullet}>{bullet}</li>
                      ))}
                    </ul>
                  )}
                </section>
              ))}
            </div>

            <aside className="mt-12 border-y border-border py-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-medium">对本文档有疑问？</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    请附上页面名称、账号邮箱和具体问题。
                  </p>
                </div>
                <a
                  href={LEGAL_CONTACT_HREF}
                  className="inline-flex min-h-10 items-center gap-2 text-sm font-medium text-[var(--factory-accent)] hover:underline"
                >
                  <Mail className="h-4 w-4" aria-hidden="true" />
                  {LEGAL_CONTACT_EMAIL}
                </a>
              </div>
            </aside>
          </article>
        </div>
      </main>

      <PublicLegalFooter />
    </div>
  )
}
