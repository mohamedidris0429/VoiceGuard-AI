import { useEffect } from 'react'
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react'

export function cx(...classes) {
  return classes.filter(Boolean).join(' ')
}

const BUTTON_VARIANTS = {
  primary:
    'bg-accent text-[#04120A] hover:bg-[#2ee06a] shadow-[0_10px_28px_-14px_rgba(34,197,94,0.9)]',
  secondary: 'border border-white/10 bg-white/[0.04] text-ink hover:border-accent/30 hover:bg-white/[0.07]',
  ghost: 'text-muted hover:bg-white/5 hover:text-ink',
  danger: 'border border-danger/30 bg-danger/10 text-danger hover:bg-danger/20',
  teal: 'bg-teal text-[#04120A] hover:bg-[#21cbb8]',
}

const BUTTON_SIZES = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2.5 text-sm',
  lg: 'px-5 py-3 text-sm',
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  className,
  loading = false,
  disabled,
  type = 'button',
  ...props
}) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-50',
        BUTTON_VARIANTS[variant] || BUTTON_VARIANTS.primary,
        BUTTON_SIZES[size] || BUTTON_SIZES.md,
        className,
      )}
      {...props}
    >
      {loading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : null}
      {children}
    </button>
  )
}

export function Card({ children, className, ...props }) {
  return (
    <div className={cx('card p-5', className)} {...props}>
      {children}
    </div>
  )
}

const BADGE_TONES = {
  success: 'border-accent/25 bg-accent/10 text-accent',
  danger: 'border-danger/25 bg-danger/10 text-danger',
  warn: 'border-warn/25 bg-warn/10 text-warn',
  teal: 'border-teal/25 bg-teal/10 text-teal',
  neutral: 'border-white/10 bg-white/5 text-muted',
}

export function Badge({ tone = 'neutral', children, className }) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold',
        BADGE_TONES[tone] || BADGE_TONES.neutral,
        className,
      )}
    >
      {children}
    </span>
  )
}

const ALERT_TONES = {
  info: { wrap: 'border-teal/25 bg-teal/[0.07] text-teal', Icon: Info },
  success: { wrap: 'border-accent/25 bg-accent/[0.07] text-accent', Icon: CheckCircle2 },
  error: { wrap: 'border-danger/25 bg-danger/[0.08] text-danger', Icon: AlertTriangle },
  warn: { wrap: 'border-warn/25 bg-warn/[0.08] text-warn', Icon: AlertTriangle },
}

export function Alert({ tone = 'info', title, children, className, action }) {
  const config = ALERT_TONES[tone] || ALERT_TONES.info
  const Icon = config.Icon
  return (
    <div className={cx('flex gap-3 rounded-xl border p-3.5 text-sm', config.wrap, className)}>
      <Icon size={17} className="mt-0.5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1 space-y-1">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div className="text-[13px] leading-relaxed opacity-90">{children}</div> : null}
        {action ? <div className="pt-1">{action}</div> : null}
      </div>
    </div>
  )
}

export function Spinner({ size = 18, className }) {
  return <Loader2 size={size} className={cx('animate-spin text-accent', className)} aria-hidden />
}

export function LoadingBlock({ label = 'Loading…', className }) {
  return (
    <div className={cx('flex items-center justify-center gap-3 py-14 text-sm text-muted', className)}>
      <Spinner /> {label}
    </div>
  )
}

export function Skeleton({ className }) {
  return <div className={cx('animate-pulse rounded-lg bg-white/[0.06]', className)} />
}

export function EmptyState({ icon: Icon, title, description, action, className }) {
  return (
    <div className={cx('flex flex-col items-center justify-center gap-3 px-6 py-14 text-center', className)}>
      {Icon ? (
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3 text-muted">
          <Icon size={22} aria-hidden />
        </div>
      ) : null}
      <div className="space-y-1">
        <p className="text-sm font-semibold text-ink">{title}</p>
        {description ? <p className="max-w-sm text-[13px] leading-relaxed text-muted">{description}</p> : null}
      </div>
      {action}
    </div>
  )
}

export function Modal({ open, onClose, title, description, children, footer, size = 'md' }) {
  useEffect(() => {
    if (!open) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKeyDown)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previous
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-0 backdrop-blur-sm sm:items-center sm:p-6">
      <div
        className="absolute inset-0"
        onClick={() => onClose?.()}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cx(
          'relative w-full animate-fade-in rounded-t-2xl border border-white/10 bg-surface p-5 shadow-2xl sm:rounded-2xl',
          size === 'lg' ? 'sm:max-w-2xl' : 'sm:max-w-md',
        )}
      >
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-ink">{title}</h2>
            {description ? <p className="mt-1 text-[13px] text-muted">{description}</p> : null}
          </div>
          <button
            type="button"
            onClick={() => onClose?.()}
            className="rounded-lg p-1.5 text-muted transition hover:bg-white/5 hover:text-ink"
            aria-label="Close dialog"
          >
            <X size={17} />
          </button>
        </div>
        {children ? <div className="text-sm text-ink">{children}</div> : null}
        {footer ? <div className="mt-5 flex flex-wrap justify-end gap-2">{footer}</div> : null}
      </div>
    </div>
  )
}

export function Field({ label, htmlFor, hint, error, children, required }) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>
        {label} {required ? <span className="text-accent">*</span> : null}
      </label>
      {children}
      {error ? (
        <p className="mt-1.5 text-xs font-medium text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1.5 text-xs text-muted">{hint}</p>
      ) : null}
    </div>
  )
}

export function ProgressBar({ value = 0, tone = 'accent', className, showLabel = false }) {
  const clamped = Math.max(0, Math.min(100, Number(value) || 0))
  const bar = tone === 'danger' ? 'bg-danger' : tone === 'warn' ? 'bg-warn' : tone === 'teal' ? 'bg-teal' : 'bg-accent'
  return (
    <div className={cx('space-y-1.5', className)}>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className={cx('h-full rounded-full transition-[width] duration-300', bar)}
          style={{ width: `${clamped}%` }}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(clamped)}
        />
      </div>
      {showLabel ? <p className="text-right text-[11px] font-medium text-muted">{Math.round(clamped)}%</p> : null}
    </div>
  )
}

export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="space-y-1">
        {eyebrow ? (
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent/80">{eyebrow}</p>
        ) : null}
        <h1 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">{title}</h1>
        {description ? <p className="max-w-2xl text-[13px] leading-relaxed text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function StatCard({ label, value, hint, icon: Icon, tone = 'accent' }) {
  const toneRing = {
    accent: 'text-accent bg-accent/10 border-accent/20',
    teal: 'text-teal bg-teal/10 border-teal/20',
    danger: 'text-danger bg-danger/10 border-danger/20',
    warn: 'text-warn bg-warn/10 border-warn/20',
    muted: 'text-muted bg-white/5 border-white/10',
  }
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">{label}</p>
        {Icon ? (
          <span className={cx('rounded-lg border p-1.5', toneRing[tone] || toneRing.accent)}>
            <Icon size={15} aria-hidden />
          </span>
        ) : null}
      </div>
      <p className="mt-3 text-2xl font-semibold tracking-tight text-ink">{value}</p>
      {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </div>
  )
}

export function Toggle({ checked, onChange, label, description, id }) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-start justify-between gap-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
      <span className="space-y-0.5">
        <span className="block text-sm font-medium text-ink">{label}</span>
        {description ? <span className="block text-xs text-muted">{description}</span> : null}
      </span>
      <span className="relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center">
        <input
          id={id}
          type="checkbox"
          className="peer sr-only"
          checked={Boolean(checked)}
          onChange={(event) => onChange?.(event.target.checked)}
        />
        <span className="h-6 w-11 rounded-full bg-white/10 transition peer-checked:bg-accent/80" aria-hidden />
        <span className="absolute left-0.5 h-5 w-5 rounded-full bg-ink transition peer-checked:translate-x-5" aria-hidden />
      </span>
    </label>
  )
}
