import { Link } from 'react-router-dom'
import { ArrowLeft, Compass } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export default function NotFound() {
  const { isAuthenticated } = useAuth()
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 px-6 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03] text-teal">
        <Compass size={24} aria-hidden />
      </span>
      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted">Error 404</p>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">This page does not exist</h1>
        <p className="max-w-md text-[13px] leading-relaxed text-muted">
          The link may be outdated. Return to the dashboard to continue analysing recordings.
        </p>
      </div>
      <Link
        to={isAuthenticated ? '/dashboard' : '/login'}
        className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-[#04120A] transition hover:bg-[#2ee06a]"
      >
        <ArrowLeft size={15} /> {isAuthenticated ? 'Back to dashboard' : 'Go to sign in'}
      </Link>
    </div>
  )
}
