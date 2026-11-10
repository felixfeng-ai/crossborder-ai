import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Image, Sparkles, X } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useImageHistory, formatRelativeTime } from './useOnboarding'

/** 每个完成态最多展示的缩略图数量 */
const GALLERY_LIMIT = 6

/**
 * ImageHistoryGallery - 最近生成的图（Dashboard 图结果历史画廊）
 *
 * 契约：GET /api/v1/images/history → { items: [{id,prompt,status,image_urls[],model_used,error,created_at}] }
 *  - 仅展示 status==='completed' 的记录，最多 6 张网格。
 *  - 端点未接通（404/5xx/网络错误）→ 整块静默隐藏，不让页面崩（优雅降级）。
 *  - 端点通了但没有已完成图 → 空态引导文案 + 跳转图片生成页。
 * 点击缩略图弹出放大预览（轻量自实现，未引入额外依赖）。
 */
export default function ImageHistoryGallery() {
  const navigate = useNavigate()
  const [preview, setPreview] = useState<string | null>(null)
  const history = useImageHistory()

  // Esc 关闭放大预览
  useEffect(() => {
    if (!preview) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPreview(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [preview])

  // 首次加载：等结果落定（可能被判定为不可用而整块隐藏，避免闪块）
  if (history.isLoading) return null
  // 端点不可用：按契约优雅降级，隐藏该区块
  if (history.isError) return null

  const completed = (history.data ?? []).filter(
    (it) => it.status === 'completed' && Array.isArray(it.image_urls) && it.image_urls.length > 0,
  )
  const shown = completed.slice(0, GALLERY_LIMIT)

  const truncatePrompt = (p: string) => (p.length > 32 ? `${p.slice(0, 32)}…` : p)

  // 空态：端点可用但还没有生成结果 → 引导去图生成本
  if (shown.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center gap-3 py-8 text-center">
          <span className="flex h-10 w-10 items-center justify-center rounded bg-muted text-muted-foreground">
            <Image className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-medium">还没有 AI 生成的商品图</p>
            <p className="text-xs text-muted-foreground mt-1">描述一下商品，几分钟内就能看到第一张 AI 主图</p>
          </div>
          <Button size="sm" className="gap-1.5" onClick={() => navigate('/app/images')}>
            <Sparkles className="h-3.5 w-3.5" />
            去生成第一张图
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <Image className="h-4 w-4 text-muted-foreground" />
              最近生成的图
            </CardTitle>
            <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-primary" onClick={() => navigate('/app/images')}>
              去生成
              <Sparkles className="h-3.5 w-3.5 ml-1" />
            </Button>
          </div>
          <CardDescription className="text-xs">
            你最近生成的 AI 商品图 · 点击可放大查看
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {shown.map((item) => {
              const url = item.image_urls[0]
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setPreview(url)}
                  className="group relative aspect-square overflow-hidden rounded border border-border bg-muted text-left focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <img
                    src={url}
                    alt={item.prompt || 'AI 生成图'}
                    loading="lazy"
                    className="h-full w-full object-cover"
                    onError={(e) => {
                      // 图片加载失败时占位，不撑破网格
                      const el = e.currentTarget
                      el.style.display = 'none'
                    }}
                  />
                  {item.model_used && (
                    <Badge
                      variant="outline"
                      className="absolute left-1.5 top-1.5 max-w-[70%] truncate bg-background/80 backdrop-blur-sm"
                      title={item.model_used}
                    >
                      {item.model_used}
                    </Badge>
                  )}
                  <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-1.5 pb-1 pt-4">
                    <p className="truncate text-[11px] text-white">{truncatePrompt(item.prompt)}</p>
                    {item.created_at && (
                      <p className="text-[10px] text-white/70">{formatRelativeTime(item.created_at)}</p>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* 放大预览（轻量 modal：遮罩点击 / Esc 关闭） */}
      {preview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="图片放大预览"
          onClick={() => setPreview(null)}
        >
          <div className="relative max-w-3xl w-full" onClick={(e) => e.stopPropagation()}>
            <img
              src={preview}
              alt="放大预览"
              className="max-h-[85vh] w-full rounded-lg border border-border bg-[var(--factory-ground)] object-contain"
            />
            <Button
              variant="ghost"
              size="icon"
              className="absolute -top-11 right-0 h-8 w-8 text-white hover:bg-white/10 hover:text-white"
              onClick={() => setPreview(null)}
              aria-label="关闭预览"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </>
  )
}
