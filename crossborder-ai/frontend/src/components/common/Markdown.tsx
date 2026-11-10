import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

/**
 * Markdown - LLM 输出渲染组件
 *
 * react-markdown 默认不渲染原始 HTML（LLM 输出不可信 → 天然防 XSS）。
 * 样式走品牌琥珀金主题：标题带主色左竖线、表格带边框、列表缩进。
 */

const components: Components = {
  h1: ({ node, ...props }) => <h1 className="text-base font-bold text-primary mt-3 mb-2" {...props} />,
  h2: ({ node, ...props }) => (
    <h2 className="text-sm font-semibold border-l-2 border-primary/40 pl-2 mt-3 mb-1.5" {...props} />
  ),
  h3: ({ node, ...props }) => <h3 className="text-sm font-semibold mt-3 mb-1.5" {...props} />,
  h4: ({ node, ...props }) => <h4 className="text-sm font-semibold mt-2 mb-1" {...props} />,
  p: ({ node, ...props }) => <p className="my-1.5 leading-relaxed break-words" {...props} />,
  table: ({ node, ...props }) => (
    <div className="overflow-x-auto my-2">
      <table className="w-full text-xs border-collapse" {...props} />
    </div>
  ),
  thead: ({ node, ...props }) => <thead className="bg-muted" {...props} />,
  tr: ({ node, ...props }) => <tr className="even:bg-muted/30" {...props} />,
  th: ({ node, ...props }) => (
    <th className="border px-2 py-1.5 text-left font-medium whitespace-nowrap" {...props} />
  ),
  td: ({ node, ...props }) => <td className="border px-2 py-1.5 align-top" {...props} />,
  ul: ({ node, ...props }) => <ul className="list-disc pl-5 my-1.5 space-y-0.5" {...props} />,
  ol: ({ node, ...props }) => <ol className="list-decimal pl-5 my-1.5 space-y-0.5" {...props} />,
  li: ({ node, ...props }) => <li className="leading-relaxed" {...props} />,
  blockquote: ({ node, ...props }) => (
    <blockquote className="border-l-2 border-primary/40 pl-3 my-2 text-muted-foreground" {...props} />
  ),
  code: ({ node, ...props }) => <code className="bg-muted px-1 py-0.5 rounded text-xs" {...props} />,
  pre: ({ node, ...props }) => (
    <pre className="bg-muted p-3 rounded-lg overflow-x-auto text-xs my-2" {...props} />
  ),
  strong: ({ node, ...props }) => <strong className="font-semibold" {...props} />,
  a: ({ node, ...props }) => (
    <a target="_blank" rel="noopener noreferrer" className="text-primary underline break-all" {...props} />
  ),
}

export default function Markdown({
  content,
  inverted = false,
}: {
  content: string
  /** 置于主色底气泡内（如用户消息 bg-primary）时置 true。
   *  此时链接若仍用 text-primary 会与背景同色而不可见，需改为反色。 */
  inverted?: boolean
}) {
  return (
    // text-foreground：body 的 @apply text-foreground 未编译，裸文本会回退黑色看不清，这里显式声明
    // [&_a:] 后代选择器特异性(0,1,1)高于 a 自身的 .text-primary(0,1,0)，可稳定覆盖链接颜色
    <div
      className={`text-sm ${
        inverted
          ? 'text-primary-foreground [&_a]:text-primary-foreground [&_code]:bg-black/10 [&_pre]:bg-black/10'
          : 'text-foreground'
      }`}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
