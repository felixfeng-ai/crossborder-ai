import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Calculator,
  DollarSign,
  Percent,
  Truck,
  Megaphone,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Wallet,
  HelpCircle,
  Loader2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import apiClient from '@/api/client'

/**
 * LedgerPage - 净利计算器（F9 Ledger）
 *
 * 功能：
 * 输入售价、成本、费率，自动计算净利和利润率
 *
 * 公式：
 *   售价(CNY) = 售价(外币) × 汇率
 *   平台费 = 售价(CNY) × 平台费率
 *   总成本 = 平台费 + 商品成本 + 运费 + 广告费
 *   净利 = 售价(CNY) - 总成本
 *   利润率 = (净利 / 售价(CNY)) × 100%
 */

// ── 类型定义 ──────────────────────────────────────────────────
/** 计算输入参数 */
interface ProfitInput {
  selling_price: number       // 售价（外币）
  platform_fee_rate: number   // 平台费率（小数，如 0.15）
  product_cost: number        // 商品成本（CNY）
  shipping_cost: number       // 运费（CNY）
  advertising_cost: number    // 广告费（CNY）
  exchange_rate: number       // 汇率
}

/** 计算结果 */
interface ProfitResult {
  selling_price_cny: number   // 折合人民币的售价
  platform_fee: number        // 平台费
  total_cost: number          // 总成本
  net_profit: number          // 净利
  profit_margin: number       // 利润率（百分比）
}


export default function LedgerPage() {
  // ── 表单状态 ──────────────────────────────────────────────
  const [form, setForm] = useState<ProfitInput>({
    selling_price: 19.99,
    platform_fee_rate: 0.15,
    product_cost: 30,
    shipping_cost: 15,
    advertising_cost: 5,
    exchange_rate: 7.2,
  })

  // ── 计算结果状态 ──────────────────────────────────────────
  const [result, setResult] = useState<ProfitResult | null>(null)

  // ── Mutation：调用后端计算 ────────────────────────────────
  const calculateMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post<ProfitResult>('/ledger/calculate', form)
      return res.data
    },
    onSuccess: (data) => {
      setResult(data)
    },
  })

  // ── 更新表单字段的通用函数 ────────────────────────────────
  const updateField = (field: keyof ProfitInput, value: string) => {
    setForm((prev) => ({ ...prev, [field]: parseFloat(value) || 0 }))
  }

  // ── 切换是否使用后端计算 ──────────────────────────────────
  // 前端也可以直接算，但调后端 API 更规范，也展示了完整的前后端交互
  const handleCalculate = () => {
    calculateMutation.mutate()
  }

  // ── 利润率颜色 ────────────────────────────────────────────
  const marginColor = (margin: number) => {
    if (margin >= 30) return 'text-[var(--factory-success)]'
    if (margin >= 15) return 'text-[var(--factory-warning)]'
    return 'text-destructive'
  }

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="max-w-4xl mx-auto space-y-6">
      {/* ── 页面标题 ────────────────────────────────────────── */}
      <div className="text-center">
        <h1 className="text-2xl font-bold tracking-tight flex items-center justify-center gap-2">
          <Calculator className="h-6 w-6 text-primary" />
          净利计算器（F9 Ledger）
        </h1>
        <p className="text-muted-foreground mt-1">
          输入售价、成本、费率，自动计算每件商品的净利润和利润率
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* ── 左侧：输入表单 ────────────────────────────────── */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">收入</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* 售价 */}
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  <DollarSign className="h-3 w-3" />
                  售价（外币）
                  <span className="text-xs text-muted-foreground font-normal">如 19.99 USD</span>
                </Label>
                <Input
                  type="number" step="0.01" min="0"
                  value={form.selling_price}
                  onChange={(e) => updateField('selling_price', e.target.value)}
                />
              </div>

              {/* 汇率 */}
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  <RefreshCw className="h-3 w-3" />
                  汇率
                  <span className="text-xs text-muted-foreground font-normal">1 外币 = ? CNY</span>
                </Label>
                <Input
                  type="number" step="0.01" min="0"
                  value={form.exchange_rate}
                  onChange={(e) => updateField('exchange_rate', e.target.value)}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">成本</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* 平台费率 */}
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  <Percent className="h-3 w-3" />
                  平台费率
                  <span className="text-xs text-muted-foreground font-normal">
                    Amazon 约 15%，eBay 约 13%
                  </span>
                </Label>
                <div className="relative">
                  <Input
                    type="number" step="0.01" min="0" max="1"
                    value={form.platform_fee_rate}
                    onChange={(e) => updateField('platform_fee_rate', e.target.value)}
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                    {(form.platform_fee_rate * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* 商品成本 */}
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  <Wallet className="h-3 w-3" />
                  商品成本（CNY）
                </Label>
                <Input
                  type="number" step="0.01" min="0"
                  value={form.product_cost}
                  onChange={(e) => updateField('product_cost', e.target.value)}
                />
              </div>

              {/* 运费 */}
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  <Truck className="h-3 w-3" />
                  运费（CNY）
                </Label>
                <Input
                  type="number" step="0.01" min="0"
                  value={form.shipping_cost}
                  onChange={(e) => updateField('shipping_cost', e.target.value)}
                />
              </div>

              {/* 广告费 */}
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  <Megaphone className="h-3 w-3" />
                  广告费（CNY）
                </Label>
                <Input
                  type="number" step="0.01" min="0"
                  value={form.advertising_cost}
                  onChange={(e) => updateField('advertising_cost', e.target.value)}
                />
              </div>
            </CardContent>
          </Card>

          {/* 计算按钮 */}
          <Button
            className="w-full"
            size="lg"
            onClick={handleCalculate}
            disabled={calculateMutation.isPending}
          >
            {calculateMutation.isPending ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" />计算中...</>
            ) : (
              <><Calculator className="mr-2 h-4 w-4" />计算净利润</>
            )}
          </Button>
        </div>

        {/* ── 右侧：结果展示 ────────────────────────────────── */}
        <div className="space-y-4">
          {/* 净利总览卡片 */}
          {result && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="space-y-4"
            >
              {/* 核心指标：净利 + 利润率 */}
              <Card className={`border-2 ${
                result.profit_margin >= 30 ? 'border-emerald-500/30' :
                result.profit_margin >= 15 ? 'border-amber-500/30' :
                'border-destructive/30'
              }`}>
                <CardContent className="pt-6 text-center">
                  <p className="text-sm text-muted-foreground mb-2">每件商品净利润</p>
                  <p className={`text-4xl font-bold ${
                    result.net_profit >= 0 ? 'text-[var(--factory-success)]' : 'text-destructive'
                  }`}>
                    {result.net_profit >= 0 ? '+' : ''}¥{result.net_profit.toFixed(2)}
                  </p>
                  <div className="flex items-center justify-center gap-2 mt-3">
                    <span className="text-sm text-muted-foreground">利润率</span>
                    <span className={`text-lg font-bold ${marginColor(result.profit_margin)}`}>
                      {result.profit_margin >= 0 ? (
                        <TrendingUp className="h-4 w-4 inline mr-1" />
                      ) : (
                        <TrendingDown className="h-4 w-4 inline mr-1" />
                      )}
                      {result.profit_margin.toFixed(1)}%
                    </span>
                  </div>
                </CardContent>
              </Card>

              {/* 详细数据 */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">费用明细</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {/* 收入 */}
                  <div className="flex justify-between items-center py-2 border-b">
                    <span className="text-sm text-muted-foreground">折合人民币售价</span>
                    <span className="font-semibold text-[var(--factory-success)]">
                      ¥{result.selling_price_cny.toFixed(2)}
                    </span>
                  </div>

                  {/* 各项费用 */}
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">平台费（{(form.platform_fee_rate * 100).toFixed(0)}%）</span>
                      <span className="text-destructive">-¥{result.platform_fee.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">商品成本</span>
                      <span className="text-destructive">-¥{form.product_cost.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">运费</span>
                      <span className="text-destructive">-¥{form.shipping_cost.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">广告费</span>
                      <span className="text-destructive">-¥{form.advertising_cost.toFixed(2)}</span>
                    </div>
                  </div>

                  {/* 分割线 */}
                  <div className="border-t pt-3">
                    <div className="flex justify-between items-center">
                      <span className="text-sm font-medium">总成本</span>
                      <span className="font-bold text-destructive">
                        -¥{result.total_cost.toFixed(2)}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* 空状态提示 */}
          {!result && (
            <div className="space-y-4">
              <Card>
                <CardContent className="py-12 text-center text-muted-foreground">
                  <Calculator className="h-12 w-12 mx-auto mb-3 opacity-30" />
                  <p className="text-sm">填写左侧表单，点击「计算净利润」</p>
                  <p className="text-xs mt-1">系统会自动计算每件商品的净利和利润率</p>
                </CardContent>
              </Card>

              {/* 使用说明 */}
              <Card className="bg-muted/30">
                <CardHeader>
                  <CardTitle className="text-sm flex items-center gap-2">
                    <HelpCircle className="h-4 w-4" />
                    使用说明
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-sm space-y-2 text-muted-foreground">
                  <p><strong>净利计算公式：</strong></p>
                  <p className="pl-4 border-l-2">
                    收入 = 售价 × 汇率（折合 CNY）<br />
                    支出 = 平台费 + 商品成本 + 运费 + 广告费<br />
                    净利 = 收入 - 支出
                  </p>
                  <p className="mt-2">
                    <strong>平台参考费率：</strong><br />
                    Amazon: 15%、eBay: 13.25%、Shopify: 2.9%+$0.30、Etsy: 6.5%
                  </p>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}
