import { toErrorMessage } from '@/utils/errorMessage'


/** SKU 保存失败时优先展示后端可读错误，未知异常使用稳定兜底文案。 */
export function variantSaveErrorMessage(error: unknown): string {
  return toErrorMessage(error, '保存变体失败，请稍后重试')
}
