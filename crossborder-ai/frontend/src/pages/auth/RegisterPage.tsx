import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowLeft, Eye, EyeOff } from 'lucide-react'
import { AuthLayout } from '@/components/auth/AuthLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import LegalConsent from '@/components/legal/LegalConsent'
import { useAuthStore } from '@/stores/authStore'

const registerSchema = z
  .object({
    email: z.string().email('邮箱格式不正确'),
    username: z.string().min(3, '用户名至少 3 个字符').max(100),
    password: z.string().min(6, '密码至少 6 个字符'),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: '两次密码不一致',
    path: ['confirmPassword'],
  })

type RegisterForm = z.infer<typeof registerSchema>

export default function RegisterPage() {
  const navigate = useNavigate()
  const { register: registerUser, isLoading, error, clearError } = useAuthStore()
  const [step, setStep] = useState(1)
  const [showPassword, setShowPassword] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
    trigger,
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      email: '',
      username: '',
      password: '',
      confirmPassword: '',
    },
  })

  const onSubmit = async (data: RegisterForm) => {
    clearError()
    try {
      await registerUser({
        email: data.email,
        username: data.username,
        password: data.password,
      })
      navigate('/app/dashboard')
    } catch {
      // 错误由 authStore 统一转换为用户可读中文。
    }
  }

  const nextStep = async () => {
    const ok = await trigger(['email', 'username'])
    if (ok) setStep(2)
  }

  const inputClassName =
    'h-11 rounded-[5px] border-[var(--factory-line-strong)] bg-[var(--factory-panel)]'

  return (
    <AuthLayout>
      <div className="flex items-center gap-1.5 font-mono text-[11px] text-[var(--factory-accent)]">
        <span className="h-[5px] w-[5px] rounded-full bg-[var(--factory-accent)]" />
        AI 决策工作台 · 免费开始
      </div>

      <h1 className="mt-4 text-[30px] font-semibold leading-[1.35]">
        创建 VeyaShip 账号
      </h1>
      <p className="mt-2 text-[13px] leading-7 text-muted-foreground">
        从第一条商品链路开始，让 AI 参与判断、生成与执行。
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

        {step === 1 ? (
          <>
            <div className="space-y-2">
              <Label htmlFor="register-email" className="text-xs font-medium">
                邮箱
              </Label>
              <Input
                id="register-email"
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                className={inputClassName}
                {...register('email')}
              />
              {errors.email && <p className="text-xs text-[var(--factory-coral)]">{errors.email.message}</p>}
            </div>

            <div className="space-y-2">
              <Label htmlFor="register-username" className="text-xs font-medium">
                用户名
              </Label>
              <Input
                id="register-username"
                autoComplete="username"
                placeholder="your-name"
                className={inputClassName}
                {...register('username')}
              />
              {errors.username && <p className="text-xs text-[var(--factory-coral)]">{errors.username.message}</p>}
            </div>

            <Button type="button" onClick={nextStep} className="mt-1 h-11 w-full rounded-[5px] text-[13px] font-semibold">
              继续
            </Button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setStep(1)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              返回账号信息
            </button>

            <div className="space-y-2">
              <Label htmlFor="register-password" className="text-xs font-medium">
                密码
              </Label>
              <div className="relative">
                <Input
                  id="register-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  placeholder="至少 6 位"
                  className={`${inputClassName} pr-11`}
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

            <div className="space-y-2">
              <Label htmlFor="register-confirm-password" className="text-xs font-medium">
                确认密码
              </Label>
              <Input
                id="register-confirm-password"
                type="password"
                autoComplete="new-password"
                placeholder="再次输入密码"
                className={inputClassName}
                {...register('confirmPassword')}
              />
              {errors.confirmPassword && (
                <p className="text-xs text-[var(--factory-coral)]">
                  {errors.confirmPassword.message}
                </p>
              )}
            </div>

            <Button
              type="submit"
              disabled={isLoading}
              className="mt-1 h-11 w-full rounded-[5px] text-[13px] font-semibold"
            >
              {isLoading ? '注册中…' : '创建账号'}
            </Button>
          </>
        )}
      </form>

      <LegalConsent mode="register" />

      <div className="mt-4 flex items-center justify-between gap-4 text-[11px] text-muted-foreground">
        <Link to="/" className="hover:text-foreground">
          返回首页
        </Link>
        <span>
          已有账号？
          <Link to="/login" className="font-medium text-foreground hover:underline">
            登录
          </Link>
        </span>
      </div>

      <p className="mt-6 border-t border-border pt-4 text-[11px] leading-6 text-muted-foreground">
        注册后可使用 AI 品类分析、Listing 生成、图片任务、合规检查与商品上架能力。
      </p>
    </AuthLayout>
  )
}
