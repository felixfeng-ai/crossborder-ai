import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Upload,
  FileText,
  Loader2,
  CheckCircle2,
  AlertCircle,
  XCircle,
  Clock,
  Play,
  List,
  Sparkles,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import apiClient from '@/api/client'
import { toErrorMessage } from '@/utils/errorMessage'

/**
 * BatchPage - 批量任务管理（F4 Batch）
 *
 * 功能：
 * 1. 上传 CSV 文件 → 逐行解析为批量任务
 * 2. 查看任务列表（分页，按状态过滤）
 * 3. 手动触发处理单条任务
 *
 * CSV 格式要求：
 *   title, url, price, description
 *   商品A, https://..., 29.99, 描述文字
 */

// ── 类型定义 ──────────────────────────────────────────────────
/** 批量任务的数据结构，对应后端 BatchJob 模型 */
interface BatchJob {
  id: string
  row_index: number
  title: string | null
  url: string | null
  product_id: string | null
  listing_id: string | null
  status: string        // pending | processed | failed
  error: string | null
  created_at: string
  processed_at: string | null
}

/** 任务列表分页响应 */
interface JobListResponse {
  items: BatchJob[]
  total: number
  page: number
  page_size: number
  total_pages: number
}


export default function BatchPage() {
  const queryClient = useQueryClient()

  // ── 状态管理 ──────────────────────────────────────────────
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string | null>(null)

  // ── 查询：获取任务列表 ────────────────────────────────────
  const { data, isLoading } = useQuery<JobListResponse>({
    queryKey: ['batch-jobs', page, statusFilter],
    queryFn: async () => {
      const params: Record<string, unknown> = { page, page_size: 20 }
      if (statusFilter) params.status_filter = statusFilter
      const res = await apiClient.get('/batch/jobs', { params })
      return res.data
    },
  })

  // ── Mutation：上传 CSV 文件 ────────────────────────────────
  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const res = await apiClient.post('/batch/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return res.data
    },
    onSuccess: () => {
      // 上传成功后刷新列表，回到第一页
      setPage(1)
      queryClient.invalidateQueries({ queryKey: ['batch-jobs'] })
    },
  })

  // ── Mutation：处理单条任务 ────────────────────────────────
  const processMutation = useMutation({
    mutationFn: async (jobId: string) => {
      const res = await apiClient.post(`/batch/process/${jobId}`)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batch-jobs'] })
    },
  })

  const processAiMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post('/batch/process-ai')
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batch-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
  })

  const hasPending = data?.items?.some((job) => job.status === 'pending') ?? false

  // ── 文件上传处理 ──────────────────────────────────────────
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      uploadMutation.mutate(file)
    }
    // 清空 input 值，允许重复上传同一文件
    e.target.value = ''
  }

  // ── 状态徽章颜色映射 ──────────────────────────────────────
  const statusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return <Badge variant="outline" className="gap-1"><Clock className="h-3 w-3" />等待处理</Badge>
      case 'processed':
        return <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-500/20 gap-1">
          <CheckCircle2 className="h-3 w-3" />已处理
        </Badge>
      case 'failed':
        return <Badge variant="destructive" className="gap-1"><XCircle className="h-3 w-3" />失败</Badge>
      default:
        return <Badge variant="secondary">{status}</Badge>
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      {/* ── 页面标题 ────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <FileText className="h-6 w-6 text-primary" />
            批量任务（F4 Batch）
          </h1>
          <p className="text-muted-foreground">
            上传 CSV 文件，批量导入商品并生成合规 Listing。
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={!hasPending || processAiMutation.isPending}
          onClick={() => processAiMutation.mutate()}
        >
          {processAiMutation.isPending
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : <Sparkles className="h-4 w-4" />}
          AI 批量生成
        </Button>
      </div>

      {processAiMutation.isSuccess && (
        <p className="text-sm text-emerald-600 flex items-center gap-1">
          <CheckCircle2 className="h-4 w-4" />
          {processAiMutation.data?.message || '批量生成完成'}
        </p>
      )}
      {processAiMutation.isError && (
        <p className="text-sm text-destructive flex items-center gap-1">
          <AlertCircle className="h-4 w-4" />
          {toErrorMessage(processAiMutation.error, '批量生成失败')}
        </p>
      )}

      {/* ── 上传区域 ────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <Upload className="h-4 w-4" />
            上传 CSV 文件
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* 文件选择按钮（原生 input 隐藏，用 Button 触发） */}
          <div className="flex items-center gap-4">
            <Button
              variant="outline"
              disabled={uploadMutation.isPending}
              onClick={() => document.getElementById('csv-upload')?.click()}
            >
              {uploadMutation.isPending ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />上传中...</>
              ) : (
                <><Upload className="mr-2 h-4 w-4" />选择 CSV 文件</>
              )}
            </Button>
            <input
              id="csv-upload"
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleFileUpload}
            />
            <span className="text-sm text-muted-foreground">
              支持 .csv 格式，需包含 title, url, price, description 列
            </span>
          </div>

          {/* 上传成功提示 */}
          {uploadMutation.isSuccess && (
            <div className="flex items-center gap-2 text-sm text-emerald-600">
              <CheckCircle2 className="h-4 w-4" />
              {uploadMutation.data?.message || '上传成功'}
            </div>
          )}

          {/* 上传失败提示 */}
          {uploadMutation.isError && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" />
              {toErrorMessage(uploadMutation.error, '上传失败')}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── 任务列表 ────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <List className="h-4 w-4" />
              任务列表
            </CardTitle>

            {/* 状态过滤按钮组 */}
            <div className="flex gap-1">
              {[null, 'pending', 'processed', 'failed'].map((s) => (
                <Button
                  key={s || 'all'}
                  variant={statusFilter === s ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => { setStatusFilter(s); setPage(1) }}
                >
                  {s === null ? '全部' : s === 'pending' ? '等待中' : s === 'processed' ? '已完成' : '失败'}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {/* 加载中状态 */}
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : data?.items?.length ? (
            <>
              {/* 任务表格 */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-2 font-medium">#</th>
                      <th className="pb-2 font-medium">标题</th>
                      <th className="pb-2 font-medium">链接</th>
                      <th className="pb-2 font-medium">状态</th>
                      <th className="pb-2 font-medium">错误信息</th>
                      <th className="pb-2 font-medium">创建时间</th>
                      <th className="pb-2 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((job) => (
                      <tr key={job.id} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="py-2 pr-2 text-muted-foreground">{job.row_index}</td>
                        <td className="py-2 pr-2 max-w-[200px] truncate">{job.title || '-'}</td>
                        <td className="py-2 pr-2 max-w-[150px] truncate">
                          {job.url ? (
                            <a href={job.url} target="_blank" rel="noopener noreferrer"
                              className="text-primary hover:underline">
                              {job.url.slice(0, 30)}...
                            </a>
                          ) : '-'}
                        </td>
                        <td className="py-2 pr-2">{statusBadge(job.status)}</td>
                        <td className="py-2 pr-2 max-w-[200px] truncate text-destructive text-xs">
                          {job.error || '-'}
                        </td>
                        <td className="py-2 pr-2 text-muted-foreground text-xs">
                          {new Date(job.created_at).toLocaleString('zh-CN')}
                        </td>
                        <td className="py-2">
                          {/* 只有 pending 状态的任务可以手动触发处理 */}
                          {job.status === 'pending' && (
                            <Button
                              variant="ghost"
                              size="icon"
                              title="处理此任务"
                              disabled={processMutation.isPending}
                              onClick={() => processMutation.mutate(job.id)}
                            >
                              <Play className="h-4 w-4 text-primary" />
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* ── 分页 ────────────────────────────────────── */}
              {data.total_pages > 1 && (
                <div className="flex items-center justify-center gap-2 mt-4">
                  <Button
                    variant="outline" size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage(page - 1)}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-sm text-muted-foreground px-2">
                    {page} / {data.total_pages}（共 {data.total} 条）
                  </span>
                  <Button
                    variant="outline" size="sm"
                    disabled={page >= data.total_pages}
                    onClick={() => setPage(page + 1)}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </>
          ) : (
            /* 空状态 */
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <FileText className="h-12 w-12 mb-3 opacity-50" />
              <p className="text-sm">暂无批量任务</p>
              <p className="text-xs mt-1">上传 CSV 文件后，任务会显示在这里</p>
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  )
}
