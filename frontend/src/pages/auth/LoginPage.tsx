/**
 * LoginPage — refined sign-in experience.
 */
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

const loginSchema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
})

type LoginFormValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const { login } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const [serverError, setServerError] = useState<string | null>(null)

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/dashboard'

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = async (values: LoginFormValues) => {
    setServerError(null)
    try {
      await login(values)
      toast.success('Welcome back!')
      navigate(from, { replace: true })
    } catch (err: unknown) {
      const message =
        (err as { message?: string })?.message ?? 'Login failed. Please try again.'
      setServerError(message)
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Brand panel */}
      <div className="relative hidden w-[45%] overflow-hidden bg-sidebar-gradient lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(37,99,235,0.15),transparent_50%)]" />
        <div className="relative">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-gradient text-sm font-bold text-white shadow-glow">
            SS
          </div>
          <h1 className="mt-8 text-3xl font-semibold tracking-tight text-white">StockSense</h1>
          <p className="mt-3 max-w-sm text-base leading-relaxed text-slate-400">
            Inventory intelligence for teams who need to know what to reorder, what is at risk, and what is expiring.
          </p>
        </div>
        <p className="relative text-xs text-slate-600">
          Know your stock. Prevent waste. Reorder with confidence.
        </p>
      </div>

      {/* Form panel */}
      <div className="flex flex-1 items-center justify-center bg-surface-muted px-6 py-12">
        <div className="w-full max-w-[400px]">
          <div className="mb-8 lg:hidden">
            <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-brand-gradient text-sm font-bold text-white">
              SS
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">StockSense</h1>
          </div>

          <div className="card">
            <h2 className="text-xl font-semibold tracking-tight text-slate-900">Sign in</h2>
            <p className="mt-1 text-sm text-slate-500">Enter your credentials to access your workspace.</p>

            {serverError && (
              <div
                role="alert"
                className="mt-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
              >
                {serverError}
              </div>
            )}

            <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 space-y-5">
              <div>
                <label htmlFor="email" className="form-label">Email address</label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  className="input-base"
                  aria-describedby={errors.email ? 'email-error' : undefined}
                  aria-invalid={!!errors.email}
                  {...register('email')}
                />
                {errors.email && (
                  <p id="email-error" className="form-error">{errors.email.message}</p>
                )}
              </div>

              <div>
                <label htmlFor="password" className="form-label">Password</label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  className="input-base"
                  aria-describedby={errors.password ? 'password-error' : undefined}
                  aria-invalid={!!errors.password}
                  {...register('password')}
                />
                {errors.password && (
                  <p id="password-error" className="form-error">{errors.password.message}</p>
                )}
              </div>

              <button type="submit" disabled={isSubmitting} className="btn-primary w-full">
                {isSubmitting ? 'Signing in…' : 'Sign in'}
              </button>
            </form>

            <p className="mt-6 text-center text-sm text-slate-500">
              Don&apos;t have an account?{' '}
              <Link to="/register" className="font-semibold text-brand-600 hover:text-brand-700">
                Register
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
