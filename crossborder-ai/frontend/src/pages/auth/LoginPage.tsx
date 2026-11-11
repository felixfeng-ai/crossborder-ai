import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Eye, EyeOff } from 'lucide-react'
import { AuthLayout } from '@/components/auth/AuthLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import LegalConsent from '@/components/legal/LegalConsent'
import { useAuthStore } from '@/stores/authStore'

const loginSchema = z.object({
  email: z.string().email('邮箱格式不正确'),
  password: z.string().min(1, '请输入密码'),
})

type LoginForm = z.infer<typeof loginSchema>

export default function LoginPage() {
  const navigate = useNavigate()
  const { login, isLoading, error, clearError } = useAuthStore()
  const [showPassword, setShowPassword] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  })

  const onSubmit = async (data: LoginForm) => {
    clearError()
    try {
      await login(data.email, data.password)
      navigate('/app/dashboard')
    } catch {
      // 错误由 authStore 统一转换为用户可读中文。
    }
  }

  return (
    <AuthLayout>
      <div className="flex items-center gap-1.5 font-mono text-[11px] text-[var(--factory-accent)]">
        <span className="h-[5px] w-[5px] rounded-full bg-[var(--factory-accent)]" />
        AI 决策工作台 · 安全登录
      </div>

      <h1 className="mt-4 text-[30px] font-semibold leading-[1.35]">
        登录 VeyaShip
      </h1>
      <p className="mt-2 text-[13px] leading-7 text-muted-foreground">
        继续你的 AI 跨境决策、内容生成与商品上架任务。
      </p>

      <form onSubmit={handleSubmit(onSubmit)} className="mt-8 space-y-[18px]">
        {error && (
          <div
            role="alert"
            aria-live="polite"
            className="rounded-[5px] border border-[color:rgba(217,139,112,0.32)] bg-[color:rgba(217,139,112,0.1)] p-3 text-sm text-[var(--factory-coral)]"
          >
            {error}
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="email" className="text-xs font-medium">
            邮箱
          </Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            className="h-11 rounded-[5px] border-[var(--factory-line-strong)] bg-[var(--factory-panel)]"
            {...register('email')}
          />
          {errors.email && <p className="text-xs text-[var(--factory-coral)]">{errors.email.message}</p>}
        </div>

        <div className="space-y-2">
          <Label htmlFor="password" className="text-xs font-medium">
            密码
          </Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              placeholder="输入密码"
              className="h-11 rounded-[5px] border-[var(--factory-line-strong)] bg-[var(--factory-panel)] pr-11"
              {...register('password')}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded text-muted-foreground hover:text-foreground"
              aria-label={showPassword ? '隐藏密码' : '显示密码'}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {errors.password && <p className="text-xs text-[var(--factory-coral)]">{errors.password.message}</p>}
        </div>

        <Button
          type="submit"
          disabled={isLoading}
          className="mt-1 h-11 w-full rounded-[5px] text-[13px] font-semibold"
        >
          {isLoading ? '登录中…' : '登录'}
        </Button>
      </form>

      <LegalConsent mode="login" />

      <div className="mt-4 flex items-center justify-between gap-4 text-[11px] text-muted-foreground">
        <Link to="/" className="hover:text-foreground">
          返回首页
        </Link>
        <span>
          还没有账号？
          <Link to="/register" className="font-medium text-foreground hover:underline">
            注册
          </Link>
        </span>
      </div>

      <p className="mt-6 border-t border-border pt-4 text-[11px] leading-6 text-muted-foreground">
        登录后继续查看 AI 的判断依据、执行进度与渠道结果。商品、库存和发布操作共享同一工作区身份。
      </p>
    </AuthLayout>
  )
}
