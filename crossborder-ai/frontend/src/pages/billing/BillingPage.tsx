import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { CheckCircle2, CreditCard, ArrowRight, Loader2, AlertCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useAuthStore } from '@/stores/authStore'
import apiClient from '@/api/client'

interface Plan {
  id: string
  name: string
  price: number
  price_label: string
  description: string
  features: string[]
  validity_days: number
  recommended: boolean
}

interface WalletInfo {
  plan: string
  plan_credits: number
  purchased_credits: number
  total_credits: number
  plan_expires_at: string | null
  subscription_status: string
}

interface CreditPack {
  id: string
  name: string
  credits: number
  price: number
}

interface UpgradeRecord {
  id: string
  plan: string
  contact: string
  order_id: string
  amount: number
  status: 'pending' | 'approved' | 'rejected'
  note: string
  created_at: string | null
  handled_at: string | null
}

const STATUS_META: Record<UpgradeRecord['status'], { label: string; variant: 'success' | 'warning' | 'destructive' }> = {
  pending: { label: '待确认', variant: 'warning' },
  approved: { label: '已开通', variant: 'success' },
  rejected: { label: '已拒绝', variant: 'destructive' },
}

export default function BillingPage() {
  const { user } = useAuthStore()
  const queryClient = useQueryClient()
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null)
  const [selectedPack, setSelectedPack] = useState<string | null>(null)
  const [contact, setContact] = useState('')

  const { data } = useQuery({
    queryKey: ['plans'],
    queryFn: async () => {
      const res = await apiClient.get('/billing/plans')
      return res.data.plans as Plan[]
    },
  })
  const plans = data || []

  const { data: wallet } = useQuery<WalletInfo>({
    queryKey: ['billing-wallet'],
    queryFn: async () => {
      const res = await apiClient.get('/billing/wallet')
      return res.data
    },
  })

  const { data: packsData } = useQuery({
    queryKey: ['credit-packs'],
    queryFn: async () => {
      const res = await apiClient.get('/billing/credit-packs')
      return res.data.packs as CreditPack[]
    },
  })
  const packs = packsData || []

  const { data: upgradeData } = useQuery({
    queryKey: ['my-upgrades'],
    queryFn: async () => {
      const res = await apiClient.get('/billing/upgrades')
      return res.data.items as UpgradeRecord[]
    },
  })
  const upgrades = upgradeData || []

  const upgradeMutation = useMutation({
    mutationFn: async (planId: string) => {
      const res = await apiClient.post('/billing/upgrade', { plan: planId, contact })
      return res.data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['my-upgrades'] }),
  })

  const packMutation = useMutation({
    mutationFn: async (packId: string) => {
      const res = await apiClient.post('/billing/credit-packs/purchase', {
        pack_id: packId,
        contact,
      })
      return res.data
    },
  })

  if (!user) return null

  const currentPlanName = user.plan === 'standard' ? 'Standard' : user.plan === 'professional' ? 'Professional' : 'Free'

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6 max-w-3xl mx-auto">
      <div className="text-center">
        <h1 className="text-2xl font-bold tracking-tight">套餐与账单</h1>
        <p className="text-muted-foreground mt-1">
          按自然月获得积分，积分按实际功能扣减
        </p>
      </div>

      {/* 当前状态 */}
      <Card>
        <CardContent className="p-4 flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">当前套餐</p>
            <p className="text-lg font-semibold mt-0.5 capitalize">{currentPlanName}</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground">剩余积分</p>
            <p className="text-lg font-semibold mt-0.5">{wallet?.total_credits ?? user.credits ?? 0}</p>
          </div>
        </CardContent>
        <div className="grid gap-3 border-t border-border px-4 py-3 text-xs sm:grid-cols-4">
          <div>
            <p className="text-muted-foreground">套餐额度</p>
            <p className="metric-number mt-1 text-foreground">{wallet?.plan_credits ?? 0}</p>
          </div>
          <div>
            <p className="text-muted-foreground">购买积分</p>
            <p className="metric-number mt-1 text-foreground">{wallet?.purchased_credits ?? 0}</p>
          </div>
          <div>
            <p className="text-muted-foreground">套餐到期</p>
            <p className="mt-1 text-foreground">
              {wallet?.plan_expires_at
                ? new Date(wallet.plan_expires_at).toLocaleDateString('zh-CN')
                : '自然月'}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">计费方式</p>
            <p className="mt-1 text-foreground">按功能扣减</p>
          </div>
        </div>
      </Card>

      {/* 套餐对比 */}
      <div className="grid md:grid-cols-3 gap-4">
        {plans.map((plan) => {
          const isCurrent = user.plan === plan.id
          const isSelected = selectedPlan === plan.id
          return (
            <Card key={plan.id} className={`relative ${plan.recommended ? 'border-blue-500 shadow-md' : ''} ${isCurrent ? 'border-emerald-400' : ''}`}>
              {plan.recommended && !isCurrent && (
                <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-amber-500 text-white text-xs px-3 py-0.5 rounded-full whitespace-nowrap">推荐</div>
              )}
              {isCurrent && (
                <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-emerald-600 text-white text-xs px-3 py-0.5 rounded-full whitespace-nowrap">当前套餐</div>
              )}
              <CardContent className="p-5 space-y-4">
                <div>
                  <h3 className="font-semibold">{plan.name}</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">{plan.description}</p>
                  {plan.validity_days > 0 && (
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      有效期 {plan.validity_days} 天
                    </p>
                  )}
                </div>
                <div>
                  <span className="text-2xl font-bold">{plan.price === 0 ? '免费' : `¥${plan.price}`}</span>
                  {plan.price > 0 && <span className="text-sm text-muted-foreground">/月</span>}
                </div>
                <ul className="space-y-2">
                  {plan.features.map((f, i) => (
                    <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                      <CheckCircle2 className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" />{f}
                    </li>
                  ))}
                </ul>
                {!isCurrent && plan.price > 0 && (
                  <Button
                    size="sm"
                    className="w-full"
                    variant={plan.recommended ? 'default' : 'outline'}
                    onClick={() => setSelectedPlan(plan.id)}
                  >
                    升级到 {plan.name}
                  </Button>
                )}
                {isCurrent && <Button size="sm" className="w-full" variant="outline" disabled>当前套餐</Button>}
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* 积分包 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">超额积分包</CardTitle>
          <p className="text-xs text-muted-foreground">
            套餐积分不足时可单独购买，购买积分不随月度额度重置
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-3">
            {packs.map((pack) => (
              <button
                key={pack.id}
                type="button"
                onClick={() => setSelectedPack(pack.id)}
                className={`rounded-md border p-3 text-left transition-colors ${
                  selectedPack === pack.id
                    ? 'border-foreground bg-secondary'
                    : 'border-border hover:border-[var(--factory-line-strong)]'
                }`}
              >
                <p className="text-sm font-medium">{pack.name}</p>
                <p className="metric-number mt-2 text-lg font-semibold">{pack.credits}</p>
                <p className="text-[11px] text-muted-foreground">积分</p>
                <p className="mt-2 text-xs text-muted-foreground">¥{pack.price}</p>
              </button>
            ))}
          </div>
          {selectedPack && (
            <div className="space-y-3 border-t border-border pt-3">
              <input
                value={contact}
                onChange={(event) => setContact(event.target.value)}
                placeholder="微信 / 手机，用于付款确认"
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
              <Button
                className="w-full"
                disabled={contact.trim().length < 2 || packMutation.isPending}
                onClick={() => packMutation.mutate(selectedPack)}
              >
                {packMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                提交积分包购买申请
              </Button>
              {packMutation.data && (
                <p className="text-xs text-[var(--factory-success)]">{packMutation.data.message}</p>
              )}
              {packMutation.error && (
                <p className="text-xs text-[var(--factory-coral)]">
                  {packMutation.error instanceof Error ? packMutation.error.message : '提交失败'}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 升级流程 */}
      {selectedPlan && (
        <Card className="border-blue-600/30">
          <CardHeader>
            <CardTitle className="text-sm">升级到 {plans.find(p => p.id === selectedPlan)?.name}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!upgradeMutation.data ? (
              <>
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">请输入你的联系方式（微信或手机号），付款后客服会联系你确认升级</p>
                  <input
                    value={contact}
                    onChange={(e) => setContact(e.target.value)}
                    placeholder="微信号 / 手机号"
                    className="w-full h-10 rounded-lg border bg-background px-3 text-sm outline-none focus:border-blue-500"
                  />
                </div>
                <Button
                  className="w-full"
                  disabled={!contact.trim() || upgradeMutation.isPending}
                  onClick={() => upgradeMutation.mutate(selectedPlan)}
                >
                  {upgradeMutation.isPending ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />提交中...</> : '提交升级申请'}
                </Button>
              </>
            ) : (
              <div className="space-y-4">
                <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-700">
                  <p className="font-medium">✅ 升级申请已提交</p>
                  <p className="mt-1">{upgradeMutation.data.message}</p>
                </div>
                <div className="rounded-lg border p-4 space-y-2 text-sm">
                  <p className="font-medium">付款信息</p>
                  <p>金额：<strong>¥{upgradeMutation.data.amount}</strong></p>
                  <p>订单号：<code className="bg-muted px-1 py-0.5 rounded text-xs">{upgradeMutation.data.order_id}</code></p>
                  <p className="text-muted-foreground text-xs mt-2">转账请备注订单号，客服确认后立即升级。</p>
                </div>
                <Button variant="outline" className="w-full" onClick={() => { setSelectedPlan(null); upgradeMutation.reset() }}>
                  完成
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 我的升级申请 */}
      {upgrades.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">我的升级申请</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {upgrades.map((u) => {
              const meta = STATUS_META[u.status]
              return (
                <div key={u.id} className="rounded-lg border p-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium">
                        {u.plan === 'standard' ? 'Standard 套餐' : 'Professional 套餐'}
                      </p>
                      <Badge variant={meta.variant}>{meta.label}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1 truncate">
                      订单号 <code className="bg-muted px-1 py-0.5 rounded">{u.order_id}</code> · ¥{u.amount}
                      {u.note ? ` · ${u.note}` : ''}
                    </p>
                  </div>
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}
    </motion.div>
  )
}
