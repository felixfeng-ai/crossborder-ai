import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { BarChart3, TrendingUp, Package, FileText, Sparkles, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import apiClient from '@/api/client'

export default function AnalyticsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-analytics'],
    queryFn: async () => {
      const r = await apiClient.get('/analytics/dashboard')
      return r.data
    },
  })

  if (isLoading) return <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>

  const items = [
    { label: '商品总数', value: data?.products?.total ?? 0, icon: Package, color: 'text-[var(--factory-warning)]' },
    { label: 'Listing 总数', value: data?.listings?.total ?? 0, icon: FileText, color: 'text-[var(--factory-warning)]' },
    { label: 'AI 生成次数', value: data?.content?.total_generations ?? 0, icon: Sparkles, color: 'text-[var(--factory-warning)]' },
    { label: '已发布', value: data?.listings?.published ?? 0, icon: TrendingUp, color: 'text-[var(--factory-success)]' },
  ]

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <BarChart3 className="h-6 w-6 text-primary" />
          数据概览
        </h1>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {items.map((i) => (
          <Card key={i.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{i.label}</CardTitle>
              <i.icon className={`h-4 w-4 ${i.color}`} />
            </CardHeader>
            <CardContent><div className="text-2xl font-bold">{i.value}</div></CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader><CardTitle className="text-sm">平台分布</CardTitle></CardHeader>
        <CardContent>
          {data?.platforms && Object.keys(data.platforms).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(data.platforms).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-sm">
                  <span>{k}</span>
                  <span className="font-medium">{String(v)}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">暂无数据</p>
          )}
        </CardContent>
      </Card>
    </motion.div>
  )
}
