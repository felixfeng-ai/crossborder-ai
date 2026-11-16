/** 从商品内容页跳转图片工作台时，保留商品上下文。 */
export function buildImageWorkbenchHref(
  productId: string,
  title?: string | null,
): string {
  const params = new URLSearchParams({ product: productId })
  const normalizedTitle = String(title || '').trim()
  if (normalizedTitle) params.set('title', normalizedTitle)
  return `/app/images?${params.toString()}`
}

/** 商品标题作为图片提示词初值，用户仍可在工作台继续编辑。 */
export function imagePromptFromProductTitle(title?: string | null): string {
  return String(title || '').trim()
}
