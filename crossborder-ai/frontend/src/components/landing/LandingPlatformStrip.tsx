import { SUPPORTED_COPY_PLATFORMS } from '@/lib/landing/content'

/**
 * 平台支持从首屏移出，避免 11 个胶囊与主操作争夺视觉层级。
 */
export function LandingPlatformStrip() {
  return (
    <section
      data-landing-platforms
      className="border-b border-border bg-[var(--factory-side)]"
      aria-label="支持的平台"
    >
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
        <p className="shrink-0 text-xs font-medium text-foreground">
          11 个平台的内容发布准备
        </p>
        <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
          {SUPPORTED_COPY_PLATFORMS.map((platform) => (
            <span key={platform}>{platform}</span>
          ))}
        </div>
        <p className="text-[11px] leading-5 text-muted-foreground">
          Shopify 草稿发布 · Amazon SP-API
        </p>
      </div>
    </section>
  )
}
