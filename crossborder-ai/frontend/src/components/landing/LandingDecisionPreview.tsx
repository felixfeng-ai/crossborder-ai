import { ArrowRight, ShieldCheck, TrendingUp } from 'lucide-react'

/**
 * 首页首屏展示一个真实任务形态，而不是重复解释产品步骤。
 */
export function LandingDecisionPreview({ onContinue }: { onContinue: () => void }) {
  return (
    <aside className="landing-panel w-full overflow-hidden" aria-label="商品决策预览">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <p className="text-sm font-medium text-foreground">商品决策预览</p>
          <p className="mt-0.5 text-xs text-muted-foreground">Terra Body Oil · 美国市场</p>
        </div>
        <span className="border border-[color-mix(in_srgb,var(--factory-accent)_32%,transparent)] bg-[color-mix(in_srgb,var(--factory-accent)_10%,transparent)] px-2 py-1 text-[11px] font-medium text-[var(--factory-accent)]">
          可进入验证
        </span>
      </div>

      <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-4 p-5">
        <img
          src="/demo/terra-body-oil.webp"
          alt="Terra Body Oil 商品图"
          className="aspect-square w-full border border-border object-cover"
        />
        <div className="min-w-0">
          <h2 className="text-base font-semibold leading-6 text-foreground">
            Terra Body Oil 身体护理油
          </h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            来源商品已完成基础信息整理，下一步补齐成本、认证与目标平台规则。
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
            <span className="landing-chip px-2 py-1">身体护理</span>
            <span className="landing-chip px-2 py-1">礼赠场景</span>
            <span className="landing-chip px-2 py-1">Shopify</span>
          </div>
        </div>
      </div>

      <div className="divide-y divide-border border-t border-border">
        <div className="grid grid-cols-[104px_minmax(0,1fr)] gap-3 px-5 py-3 text-xs">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <TrendingUp className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
            市场判断
          </span>
          <span className="text-foreground">需求场景明确，可进入小批量验证</span>
        </div>
        <div className="grid grid-cols-[104px_minmax(0,1fr)] gap-3 px-5 py-3 text-xs">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
            合规提示
          </span>
          <span className="text-foreground">补充成分说明与授权依据后再发布</span>
        </div>
      </div>

      <div className="border-t border-border bg-[var(--factory-side)] px-5 py-3">
        <button
          type="button"
          onClick={onContinue}
          className="flex w-full items-center justify-between gap-3 text-left text-xs font-medium text-foreground"
        >
          查看示例决策工作流
          <ArrowRight className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
        </button>
      </div>
    </aside>
  )
}
