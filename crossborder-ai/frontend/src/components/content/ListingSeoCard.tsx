import { useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronUp, Copy, SearchCheck } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

interface ListingSeoCardProps {
  seoTitle: string
  seoDescription: string
  copied: string
  onCopy: (text: string, label: string) => void
}

export default function ListingSeoCard({
  seoTitle,
  seoDescription,
  copied,
  onCopy,
}: ListingSeoCardProps) {
  const [expanded, setExpanded] = useState(false)
  const descriptionLength = [...seoDescription].length
  const isOverLimit = descriptionLength > 160
  const canExpand = descriptionLength > 220

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <SearchCheck className="h-4 w-4 text-primary" />
          SEO 元数据
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {seoTitle && (
          <div>
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">SEO 标题</p>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0"
                aria-label="复制 SEO 标题"
                title="复制 SEO 标题"
                onClick={() => onCopy(seoTitle, 'seo_title')}
              >
                {copied === 'seo_title' ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
            <p className="break-words text-sm leading-6">{seoTitle}</p>
          </div>
        )}

        {seoDescription && (
          <div>
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <p className="text-xs text-muted-foreground">SEO 描述</p>
                <span
                  className={`text-[11px] ${
                    isOverLimit ? 'text-[var(--factory-coral)]' : 'text-muted-foreground'
                  }`}
                >
                  {descriptionLength} 字符 · 建议 140-160
                </span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0"
                aria-label="复制 SEO 描述"
                title="复制 SEO 描述"
                onClick={() => onCopy(seoDescription, 'seo_desc')}
              >
                {copied === 'seo_desc' ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
            <p
              className={`whitespace-pre-wrap break-words text-sm leading-6 text-foreground ${
                canExpand && !expanded ? 'line-clamp-3' : ''
              }`}
            >
              {seoDescription}
            </p>
            {canExpand && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="mt-1 h-7 px-0 text-xs"
                onClick={() => setExpanded((value) => !value)}
              >
                {expanded ? <ChevronUp className="mr-1 h-3.5 w-3.5" /> : <ChevronDown className="mr-1 h-3.5 w-3.5" />}
                {expanded ? '收起 SEO 描述' : '展开完整 SEO 描述'}
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
