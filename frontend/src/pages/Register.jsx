import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Check, Lock, Mail, User } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { Alert, Button, Field } from '../components/ui'
import { ApiError } from '../services/api'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[a-zA-Z]{2,}$/

const RULES = [
  { key: 'length', label: 'At least 8 characters', test: (value) => value.length >= 8 },
  { key: 'letter', label: 'Contains a letter', test: (value) => /[A-Za-z]/.test(value) },
  { key: 'digit', label: 'Contains a number', test: (value) => /\d/.test(value) },
]

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' })
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
    if (form.name.trim().length < 2) next.name = 'Enter your name (at least 2 characters).'
    if (!EMAIL_PATTERN.test(form.email.trim())) next.email = 'Enter a valid email address.'
    if (form.password.length < 8) next.password = 'Password must be at least 8 characters.'
    else if (!/[A-Za-z]/.test(form.password) || !/\d/.test(form.password)) {
      next.password = 'Password needs at least one letter and one number.'
    }
    if (form.confirm !== form.password) next.confirm = 'Passwords do not match.'
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
      await register({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
      })
      navigate('/dashboard', { replace: true })
    } catch (error) {
      setServerError(
        error instanceof ApiError ? error.message : 'Registration failed. Please try again.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-7 space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent/80">
          Get started
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Create your account</h1>
        <p className="text-[13px] leading-relaxed text-muted">
          Analyse recordings, keep an audit trail and export PDF reports.
        </p>
      </div>

      {serverError ? (
        <Alert tone="error" className="mb-4" title="Could not create account">
          {serverError}
        </Alert>
      ) : null}

      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Field label="Full name" htmlFor="name" error={errors.name} required>
          <div className="relative">
            <User size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              id="name"
              className="input pl-10"
              placeholder="Your name"
              autoComplete="name"
              value={form.name}
              onChange={update('name')}
              aria-invalid={Boolean(errors.name)}
            />
          </div>
        </Field>

        <Field label="Email address" htmlFor="email" error={errors.email} required>
          <div className="relative">
            <Mail size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              id="email"
              type="email"
              className="input pl-10"
              placeholder="you@organisation.com"
              autoComplete="email"
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
              className="input pl-10"
              placeholder="Create a strong password"
              autoComplete="new-password"
              value={form.password}
              onChange={update('password')}
              aria-invalid={Boolean(errors.password)}
            />
          </div>
        </Field>

        <ul className="grid gap-1.5 sm:grid-cols-3">
          {RULES.map((rule) => {
            const passed = rule.test(form.password)
            return (
              <li
                key={rule.key}
                className={`flex items-center gap-1.5 text-[11px] ${passed ? 'text-accent' : 'text-muted'}`}
              >
                <Check size={12} className={passed ? 'opacity-100' : 'opacity-30'} aria-hidden />
                {rule.label}
              </li>
            )
          })}
        </ul>

        <Field label="Confirm password" htmlFor="confirm" error={errors.confirm} required>
          <div className="relative">
            <Lock size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              id="confirm"
              type="password"
              className="input pl-10"
              placeholder="Repeat your password"
              autoComplete="new-password"
              value={form.confirm}
              onChange={update('confirm')}
              aria-invalid={Boolean(errors.confirm)}
            />
          </div>
        </Field>

        <Button type="submit" className="w-full" size="lg" loading={loading}>
          {loading ? 'Creating account…' : 'Create account'}
          {!loading ? <ArrowRight size={16} /> : null}
        </Button>
      </form>

      <p className="mt-6 text-center text-[13px] text-muted">
        Already have an account?{' '}
        <Link to="/login" className="font-semibold text-accent transition hover:text-[#4ade80]">
          Sign in
        </Link>
      </p>
    </div>
  )
}
