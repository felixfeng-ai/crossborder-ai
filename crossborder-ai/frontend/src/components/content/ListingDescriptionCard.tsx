import { useMemo, useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronUp, Code2, Copy, Eye, FileText } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import Markdown from '@/components/common/Markdown'
import SafeHtml from '@/components/common/SafeHtml'
import { parseListingDescription } from '@/lib/content/listingDescription'

interface ListingDescriptionCardProps {
  description: string
  copied: string
  onCopy: (text: string, label: string) => void
}

const FORMAT_LABELS = {
  html: 'HTML 富文本',
  markdown: 'Markdown',
  plain: '纯文本',
} as const

export default function ListingDescriptionCard({
  description,
  copied,
  onCopy,
}: ListingDescriptionCardProps) {
  const parsed = useMemo(() => parseListingDescription(description), [description])
  const [view, setView] = useState<'preview' | 'source'>('preview')
  const [expanded, setExpanded] = useState(false)
  const body = parsed.detailHtml || parsed.detailMarkdown
  const copyValue = body || parsed.source
  const canCollapse = body.length > 480
  const isLongSeoSource = parsed.shortDescription.length > 240

  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-sm">
              <FileText className="h-4 w-4 text-primary" />
              商品详情
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              {FORMAT_LABELS[parsed.format]} · 预览用于复核，源码用于复制
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="复制商品详情"
            title="复制商品详情"
            onClick={() => onCopy(copyValue, 'desc')}
          >
            {copied === 'desc' ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
        </div>

        <div className="flex w-fit items-center rounded-md border bg-background p-0.5" role="group" aria-label="详情显示方式">
          <Button
            type="button"
            variant={view === 'preview' ? 'secondary' : 'ghost'}
            size="sm"
            className="h-7 gap-1.5 px-2.5 text-xs"
            aria-pressed={view === 'preview'}
            onClick={() => setView('preview')}
          >
            <Eye className="h-3.5 w-3.5" />
            预览
          </Button>
          <Button
            type="button"
            variant={view === 'source' ? 'secondary' : 'ghost'}
            size="sm"
            className="h-7 gap-1.5 px-2.5 text-xs"
            aria-pressed={view === 'source'}
            onClick={() => setView('source')}
          >
            <Code2 className="h-3.5 w-3.5" />
            源码
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {parsed.shortDescription && (
          <div className="border-l-2 border-primary/50 pl-3">
            <p className="mb-1 text-xs font-medium text-muted-foreground">简短描述</p>
            <p
              className={`whitespace-pre-wrap break-words text-sm leading-6 text-foreground ${
                isLongSeoSource ? 'line-clamp-3' : ''
              }`}
            >
              {parsed.shortDescription}
            </p>
          </div>
        )}

        {view === 'source' ? (
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-background p-3 font-mono text-xs leading-6 text-muted-foreground">
            {parsed.source || '无内容'}
          </pre>
        ) : body ? (
          <div className={!expanded && canCollapse ? 'max-h-[360px] overflow-hidden' : ''}>
            {parsed.detailHtml ? (
              <SafeHtml html={parsed.detailHtml} />
            ) : (
              <Markdown content={parsed.detailMarkdown} />
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">暂无商品详情</p>
        )}

        {view === 'preview' && canCollapse && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? <ChevronUp className="mr-1.5 h-4 w-4" /> : <ChevronDown className="mr-1.5 h-4 w-4" />}
            {expanded ? '收起详情' : '展开完整详情'}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
