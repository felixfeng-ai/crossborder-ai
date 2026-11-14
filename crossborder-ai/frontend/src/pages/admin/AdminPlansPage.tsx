import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Save, Upload } from 'lucide-react'

import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminPanel,
  AdminStatusPill,
  formatMoney,
} from './AdminPrimitives'
import type { PlanVersion, PublicPlan } from './adminTypes'

type PlanForm = {
  name: string
  rank: string
  price: string
  firstMonthPrice: string
  annualPrice: string
  annualFullPrice: string
  monthlyCredits: string
  firstMonthBonusCredits: string
  validDays: string
  features: string
}

function formFromPlan(plan: PublicPlan): PlanForm {
  return {
    name: plan.name,
    rank: String(plan.rank),
    price: String(plan.price),
    firstMonthPrice: String(plan.first_month_price),
    annualPrice: String(plan.annual_price),
    annualFullPrice: String(plan.annual_full_price),
    monthlyCredits: String(plan.monthly_credits),
    firstMonthBonusCredits: String(plan.first_month_bonus_credits),
    validDays: String(plan.validity_days),
    features: plan.features.join('\n'),
  }
}

export default function AdminPlansPage() {
  const queryClient = useQueryClient()
  const [selectedPlan, setSelectedPlan] = useState('standard')
  const [form, setForm] = useState<PlanForm | null>(null)
  const [draft, setDraft] = useState<PlanVersion | null>(null)

  const publicQuery = useQuery<{ plans: PublicPlan[] }>({
    queryKey: ['admin-public-plans'],
    queryFn: async () => {
      const response = await apiClient.get('/billing/plans')
      return response.data
    },
  })
  const catalogQuery = useQuery<{ plans: PlanVersion[] }>({
    queryKey: ['admin-plan-catalog'],
    queryFn: async () => {
      const response = await apiClient.get('/admin/catalog')
      return response.data
    },
  })

  const current = publicQuery.data?.plans.find((plan) => plan.id === selectedPlan)
  useEffect(() => {
    if (current) setForm(formFromPlan(current))
  }, [current])

  const createDraft = useMutation({
    mutationFn: async () => {
      if (!form || !current) throw new Error('套餐信息尚未加载')
      const response = await apiClient.post(`/admin/plans/${selectedPlan}/versions`, {
        name: form.name,
        description:
          selectedPlan === 'free'
            ? '试试基本功能'
            : selectedPlan === 'standard'
              ? '适合个人卖家'
              : '适合工作室与专业卖家',
        rank: Number(form.rank),
        price_cents: Math.round(Number(form.price) * 100),
        first_month_price_cents: Math.round(Number(form.firstMonthPrice) * 100),
        annual_price_cents: Math.round(Number(form.annualPrice) * 100),
        annual_full_price_cents: Math.round(Number(form.annualFullPrice) * 100),
        monthly_credits: Number(form.monthlyCredits),
        first_month_bonus_credits: Number(form.firstMonthBonusCredits),
        valid_days: Number(form.validDays),
        features: form.features
          .split('\n')
          .map((value) => value.trim())
          .filter(Boolean),
      })
      return response.data as PlanVersion
    },
    onSuccess: (version) => {
      setDraft(version)
      void queryClient.invalidateQueries({ queryKey: ['admin-plan-catalog'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-audits'] })
    },
  })

  const publishDraft = useMutation({
    mutationFn: async (versionId: string) => {
      const response = await apiClient.post(`/admin/plan-versions/${versionId}/publish`, {})
      return response.data as PlanVersion
    },
    onSuccess: () => {
      setDraft(null)
      void queryClient.invalidateQueries({ queryKey: ['admin-public-plans'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-plan-catalog'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-audits'] })
    },
  })

  if (publicQuery.isLoading) return <AdminLoading />
  if (publicQuery.isError || !publicQuery.data || !current || !form) {
    return <AdminError onRetry={() => void publicQuery.refetch()} />
  }

  const versions = (catalogQuery.data?.plans || []).filter(
    (version) => version.plan_key === selectedPlan,
  )

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="套餐管理"
        description="创建不可变版本，发布后立即影响新订单；历史订单继续使用原快照"
      />

      <div className="flex flex-wrap gap-2">
        {publicQuery.data.plans.map((plan) => (
          <button
            key={plan.id}
            type="button"
            onClick={() => {
              setSelectedPlan(plan.id)
              setDraft(null)
            }}
            className={`min-h-9 rounded-md border px-3 text-sm ${
              selectedPlan === plan.id
                ? 'border-[var(--factory-line-strong)] bg-secondary text-foreground'
                : 'border-border text-muted-foreground hover:text-foreground'
            }`}
          >
            {plan.name}
          </button>
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)]">
        <AdminPanel title="当前生效版本" description={`${current.name} · 每月 ${current.monthly_credits} 积分`}>
          <div className="grid gap-4 p-4 sm:grid-cols-2">
            {[
              ['当前月价', formatMoney(current.price)],
              ['首月价', formatMoney(current.first_month_price)],
              ['年付活动价', formatMoney(current.annual_price)],
              ['年付原价', formatMoney(current.annual_full_price)],
              ['每月积分', String(current.monthly_credits)],
              ['有效期', `${current.validity_days} 天`],
            ].map(([label, value]) => (
              <div key={label} className="border border-border bg-[var(--factory-ground)] px-3 py-3">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="metric-number mt-1 text-base font-medium">{value}</p>
              </div>
            ))}
          </div>
          <div className="border-t border-border px-4 py-3">
            <p className="text-xs text-muted-foreground">功能清单</p>
            <ul className="mt-2 space-y-1.5 text-sm text-foreground">
              {current.features.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
          </div>
        </AdminPanel>

        <AdminPanel title="创建新版本" description="先保存草稿，确认后再发布">
          <div className="space-y-4 p-4">
            <div className="grid grid-cols-2 gap-3">
              {[
                ['name', '套餐名称'],
                ['rank', '套餐等级'],
                ['price', '月价（元）'],
                ['firstMonthPrice', '首月价（元）'],
                ['annualPrice', '年付活动价'],
                ['annualFullPrice', '年付原价'],
                ['monthlyCredits', '每月积分'],
                ['firstMonthBonusCredits', '首月赠送积分'],
                ['validDays', '有效天数'],
              ].map(([field, label]) => (
                <label key={field} className="space-y-1.5 text-xs text-muted-foreground">
                  <span>{label}</span>
                  <input
                    value={form[field as keyof PlanForm]}
                    onChange={(event) =>
                      setForm((previous) =>
                        previous ? { ...previous, [field]: event.target.value } : previous,
                      )
                    }
                    inputMode={field === 'name' ? 'text' : 'decimal'}
                    className="h-9 w-full rounded-md border border-border bg-[var(--factory-ground)] px-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                  />
                </label>
              ))}
            </div>
            <label className="block space-y-1.5 text-xs text-muted-foreground">
              <span>功能清单，每行一项</span>
              <textarea
                value={form.features}
                onChange={(event) =>
                  setForm((previous) =>
                    previous ? { ...previous, features: event.target.value } : previous,
                  )
                }
                rows={6}
                className="w-full rounded-md border border-border bg-[var(--factory-ground)] px-2.5 py-2 text-sm leading-6 text-foreground outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                disabled={createDraft.isPending}
                onClick={() => createDraft.mutate()}
              >
                {createDraft.isPending ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="mr-1 h-3.5 w-3.5" />
                )}
                创建草稿
              </Button>
              {draft && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={publishDraft.isPending}
                  onClick={() => publishDraft.mutate(draft.id)}
                >
                  {publishDraft.isPending ? (
                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Upload className="mr-1 h-3.5 w-3.5" />
                  )}
                  发布版本 v{draft.version}
                </Button>
              )}
            </div>
            {(createDraft.isError || publishDraft.isError) && (
              <p role="alert" className="text-xs text-[var(--factory-coral)]">
                版本操作失败，请检查字段后重试。
              </p>
            )}
          </div>
        </AdminPanel>
      </div>

      <AdminPanel title="版本记录" description="已发布版本不可覆盖，发布新版本会自动归档旧版本">
        <div className="divide-y divide-border">
          {catalogQuery.isLoading ? (
            <AdminLoading label="正在载入套餐版本" />
          ) : versions.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">
              当前仍使用代码兜底版本，创建并发布首个版本后会出现在这里。
            </p>
          ) : (
            versions.map((version) => (
              <div
                key={version.id}
                className="grid gap-3 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_120px_160px_auto] sm:items-center"
              >
                <div>
                  <p className="text-sm font-medium">
                    v{version.version} · {version.name}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {formatMoney(version.price_cents / 100)} / 月 · {version.monthly_credits} 积分
                  </p>
                </div>
                <AdminStatusPill
                  tone={
                    version.status === 'published'
                      ? 'good'
                      : version.status === 'draft'
                        ? 'warning'
                        : 'neutral'
                  }
                >
                  {version.status === 'published'
                    ? '已发布'
                    : version.status === 'draft'
                      ? '草稿'
                      : '已归档'}
                </AdminStatusPill>
                <span className="metric-number text-xs text-muted-foreground">
                  {version.created_at.slice(0, 16)}
                </span>
                {version.status === 'draft' ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={publishDraft.isPending}
                    onClick={() => publishDraft.mutate(version.id)}
                  >
                    发布
                  </Button>
                ) : (
                  <span />
                )}
              </div>
            ))
          )}
        </div>
      </AdminPanel>
    </div>
  )
}
