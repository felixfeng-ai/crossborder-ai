import ReactMarkdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import type { Components } from 'react-markdown'

/**
 * 安全渲染 LLM 返回的 HTML 商品详情。
 * rehype-raw 负责解析 HTML，rehype-sanitize 在进入 React 前移除脚本和危险属性。
 */
const components: Components = {
  h1: ({ node, ...props }) => <h1 className="mt-5 mb-2 text-lg font-semibold first:mt-0" {...props} />,
  h2: ({ node, ...props }) => <h2 className="mt-5 mb-2 text-base font-semibold first:mt-0" {...props} />,
  h3: ({ node, ...props }) => <h3 className="mt-4 mb-1.5 text-sm font-semibold first:mt-0" {...props} />,
  p: ({ node, ...props }) => <p className="my-2 leading-7 first:mt-0 last:mb-0" {...props} />,
  ul: ({ node, ...props }) => <ul className="my-2 list-disc space-y-1 pl-5" {...props} />,
  ol: ({ node, ...props }) => <ol className="my-2 list-decimal space-y-1 pl-5" {...props} />,
  li: ({ node, ...props }) => <li className="leading-7" {...props} />,
  strong: ({ node, ...props }) => <strong className="font-semibold text-foreground" {...props} />,
  blockquote: ({ node, ...props }) => (
    <blockquote className="my-3 border-l-2 border-primary/40 pl-3 text-muted-foreground" {...props} />
  ),
  a: ({ node, ...props }) => (
    <a target="_blank" rel="noopener noreferrer" className="text-primary underline break-all" {...props} />
  ),
  table: ({ node, ...props }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-xs" {...props} />
    </div>
  ),
  th: ({ node, ...props }) => <th className="border px-2 py-1.5 text-left font-medium" {...props} />,
  td: ({ node, ...props }) => <td className="border px-2 py-1.5 align-top" {...props} />,
}

export default function SafeHtml({ html }: { html: string }) {
  return (
    <div className="text-sm text-foreground">
      <ReactMarkdown
        rehypePlugins={[rehypeRaw, [rehypeSanitize, defaultSchema]]}
        components={components}
      >
        {html}
      </ReactMarkdown>
    </div>
  )
}
