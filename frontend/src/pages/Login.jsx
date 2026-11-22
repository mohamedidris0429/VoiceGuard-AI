import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, Lock, Mail, ShieldCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { Alert, Button, Field } from '../components/ui'
import { ApiError } from '../services/api'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[a-zA-Z]{2,}$/

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ email: '', password: '' })
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState('')
  const [loading, setLoading] = useState(false)

  const update = (key) => (event) => {
    setForm((current) => ({ ...current, [key]: event.target.value }))
    setErrors((current) => ({ ...current, [key]: undefined }))
    setServerError('')
  }

  const validate = () => {
    const next = {}
    if (!form.email.trim()) next.email = 'Enter your email address.'
    else if (!EMAIL_PATTERN.test(form.email.trim())) next.email = 'Enter a valid email address.'
    if (!form.password) next.password = 'Enter your password.'
    return next
  }

  const onSubmit = async (event) => {
    event.preventDefault()
    const nextErrors = validate()
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return

    setLoading(true)
    setServerError('')
    try {
      await login(form.email.trim(), form.password)
      const destination = location.state?.from?.pathname || '/dashboard'
      navigate(destination, { replace: true })
    } catch (error) {
      setServerError(
        error instanceof ApiError ? error.message : 'Sign in failed. Please try again.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-7 space-y-2">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/20 bg-accent/[0.06] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-accent">
          <ShieldCheck size={11} /> Secure access
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Welcome back</h1>
        <p className="text-[13px] leading-relaxed text-muted">
          Sign in to analyse recordings and review your detection history.
        </p>
      </div>

      {serverError ? (
        <Alert tone="error" className="mb-4" title="Could not sign in">
          {serverError}
        </Alert>
      ) : null}

      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Field label="Email address" htmlFor="email" error={errors.email} required>
          <div className="relative">
            <Mail size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              id="email"
              type="email"
              autoComplete="email"
              className="input pl-10"
              placeholder="you@organisation.com"
              value={form.email}
              onChange={update('email')}
              aria-invalid={Boolean(errors.email)}
            />
          </div>
        </Field>

        <Field label="Password" htmlFor="password" error={errors.password} required>
          <div className="relative">
            <Lock size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              className="input pl-10"
              placeholder="Your password"
              value={form.password}
              onChange={update('password')}
              aria-invalid={Boolean(errors.password)}
            />
          </div>
        </Field>

        <Button type="submit" className="w-full" loading={loading} size="lg">
          {loading ? 'Signing in…' : 'Sign in'}
          {!loading ? <ArrowRight size={16} /> : null}
        </Button>
      </form>

      <p className="mt-6 text-center text-[13px] text-muted">
        New to VoiceGuard AI?{' '}
        <Link to="/register" className="font-semibold text-accent transition hover:text-[#4ade80]">
          Create an account
        </Link>
      </p>

      <p className="mt-6 border-t border-white/[0.06] pt-4 text-center text-[11px] leading-relaxed text-muted">
        Passwords are hashed with bcrypt and sessions use signed JWT access tokens.
      </p>
    </div>
  )
}
