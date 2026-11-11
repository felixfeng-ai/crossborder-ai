import { Link } from 'react-router-dom'

type LegalConsentProps = {
  mode: 'login' | 'register'
}

/**
 * 登录与注册共用同一法务告知，链接使用公网路由，
 * 确保用户无需登录即可在提交账号操作前查看条款。
 */
export default function LegalConsent({ mode }: LegalConsentProps) {
  const actionText = mode === 'login' ? '登录' : '创建账号'

  return (
    <p className="mt-4 text-center text-[11px] leading-6 text-muted-foreground">
      {actionText}即表示你已阅读并同意
      <Link
        to="/terms"
        className="mx-1 font-medium text-foreground underline decoration-[var(--factory-line-strong)] underline-offset-4 hover:decoration-[var(--factory-accent)]"
      >
        服务条款
      </Link>
      和
      <Link
        to="/privacy"
        className="ml-1 font-medium text-foreground underline decoration-[var(--factory-line-strong)] underline-offset-4 hover:decoration-[var(--factory-accent)]"
      >
        隐私政策
      </Link>
    </p>
  )
}
