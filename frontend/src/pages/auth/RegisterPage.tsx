/**
 * RegisterPage — creates a new STAFF account.
 *
 * Role assignment happens via Admin panel after registration.
 */
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../../api/auth'
import { useToast } from '../../context/ToastContext'

const registerSchema = z
  .object({
    full_name: z.string().max(255).optional(),
    email: z.string().email('Enter a valid email address'),
    username: z
      .string()
      .min(3, 'Username must be at least 3 characters')
      .max(100)
      .regex(/^[a-zA-Z0-9_-]+$/, 'Only letters, digits, _ and - allowed'),
    password: z.string().min(8, 'Password must be at least 8 characters').max(128),
    confirmPassword: z.string(),
  })
  .refine((v) => v.password === v.confirmPassword, {
    message: "Passwords don't match",
    path: ['confirmPassword'],
  })

type RegisterFormValues = z.infer<typeof registerSchema>

export function RegisterPage() {
  const { toast } = useToast()
  const navigate = useNavigate()
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
  })

  const onSubmit = async (values: RegisterFormValues) => {
    setServerError(null)
    try {
      await authApi.register({
        email: values.email,
        username: values.username,
        password: values.password,
        full_name: values.full_name || undefined,
      })
      toast.success('Account created! Please sign in.')
      navigate('/login')
    } catch (err: unknown) {
      const message =
        (err as { message?: string })?.message ?? 'Registration failed. Please try again.'
      setServerError(message)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mb-3 text-4xl">📦</div>
          <h1 className="text-2xl font-bold text-slate-900">StockSense</h1>
          <p className="mt-1 text-sm text-slate-500">Create your account</p>
        </div>

        <div className="card">
          <h2 className="mb-6 text-lg font-semibold text-slate-800">New account</h2>

          {serverError && (
            <div
              role="alert"
              className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700 ring-1 ring-red-200"
            >
              {serverError}
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
            {/* Full name */}
            <div>
              <label htmlFor="full_name" className="mb-1 block text-sm font-medium text-slate-700">
                Full name <span className="text-slate-400">(optional)</span>
              </label>
              <input id="full_name" type="text" className="input-base" {...register('full_name')} />
            </div>

            {/* Email */}
            <div>
              <label htmlFor="email" className="mb-1 block text-sm font-medium text-slate-700">
                Email address
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                className="input-base"
                aria-invalid={!!errors.email}
                {...register('email')}
              />
              {errors.email && (
                <p className="mt-1 text-xs text-red-600">{errors.email.message}</p>
              )}
            </div>

            {/* Username */}
            <div>
              <label htmlFor="username" className="mb-1 block text-sm font-medium text-slate-700">
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                className="input-base"
                aria-invalid={!!errors.username}
                {...register('username')}
              />
              {errors.username && (
                <p className="mt-1 text-xs text-red-600">{errors.username.message}</p>
              )}
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="mb-1 block text-sm font-medium text-slate-700">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                className="input-base"
                aria-invalid={!!errors.password}
                {...register('password')}
              />
              {errors.password && (
                <p className="mt-1 text-xs text-red-600">{errors.password.message}</p>
              )}
            </div>

            {/* Confirm password */}
            <div>
              <label
                htmlFor="confirmPassword"
                className="mb-1 block text-sm font-medium text-slate-700"
              >
                Confirm password
              </label>
              <input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                className="input-base"
                aria-invalid={!!errors.confirmPassword}
                {...register('confirmPassword')}
              />
              {errors.confirmPassword && (
                <p className="mt-1 text-xs text-red-600">{errors.confirmPassword.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white
                         hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2
                         disabled:cursor-not-allowed disabled:opacity-60 transition-colors"
            >
              {isSubmitting ? 'Creating account…' : 'Create account'}
            </button>
          </form>

          <p className="mt-4 text-center text-sm text-slate-500">
            Already have an account?{' '}
            <Link to="/login" className="font-medium text-brand-600 hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
