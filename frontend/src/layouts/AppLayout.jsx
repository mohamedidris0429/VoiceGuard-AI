import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  GitCompare,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Mic,
  Radio,
  Settings,
  ShieldCheck,
  Upload,
  X,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { Button } from '../components/ui'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/upload', label: 'Analyse audio', icon: Upload },
  { to: '/record', label: 'Live recording', icon: Mic },
  { to: '/live', label: 'Live monitor', icon: Radio },
  { to: '/compare', label: 'Comparison', icon: GitCompare },
  { to: '/history', label: 'Analysis history', icon: History },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
]

const SECONDARY_ITEMS = [
  { to: '/profile', label: 'Profile & settings', icon: Settings },
  { to: '/system', label: 'System status', icon: Activity },
]

const TITLES = {
  '/dashboard': 'Security dashboard',
  '/upload': 'Analyse audio',
  '/record': 'Live voice recording',
  '/live': 'Near-real-time monitor',
  '/compare': 'Audio comparison',
  '/history': 'Analysis history',
  '/analytics': 'Audio analytics',
  '/profile': 'Profile & settings',
  '/system': 'System status',
}

function BrandMark() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent">
        <ShieldCheck size={18} aria-hidden />
      </span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold tracking-tight text-ink">VoiceGuard AI</span>
        <span className="block text-[10px] font-medium uppercase tracking-[0.16em] text-muted">
          SIH26104
        </span>
      </span>
    </div>
  )
}

function NavSection({ items, onNavigate }) {
  return (
    <nav className="space-y-1">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition ${
              isActive
                ? 'border border-accent/25 bg-accent/[0.08] text-accent'
                : 'border border-transparent text-muted hover:bg-white/[0.04] hover:text-ink'
            }`
          }
        >
          <item.icon size={16} aria-hidden />
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}

export default function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  const initials = (user?.name || 'U')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('')

  const signOut = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const sidebar = (
    <div className="flex h-full flex-col gap-6 p-4">
      <div className="flex items-center justify-between">
        <BrandMark />
        <button
          type="button"
          className="rounded-lg p-1.5 text-muted hover:bg-white/5 hover:text-ink lg:hidden"
          onClick={() => setMenuOpen(false)}
          aria-label="Close navigation"
        >
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto">
        <NavSection items={NAV_ITEMS} onNavigate={() => setMenuOpen(false)} />
        <div className="space-y-2">
          <p className="px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted/70">
            Account
          </p>
          <NavSection items={SECONDARY_ITEMS} onNavigate={() => setMenuOpen(false)} />
        </div>
      </div>

      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">Signed in</p>
        <p className="mt-1 truncate text-[13px] font-medium text-ink">{user?.name}</p>
        <p className="truncate text-[11px] text-muted">{user?.email}</p>
        <button
          type="button"
          onClick={signOut}
          className="mt-2.5 inline-flex items-center gap-1.5 text-[12px] font-semibold text-muted transition hover:text-danger"
        >
          <LogOut size={13} /> Sign out
        </button>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
      <aside className="sticky top-0 hidden h-screen border-r border-white/[0.06] bg-surface/40 backdrop-blur lg:block">
        {sidebar}
      </aside>

      {menuOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setMenuOpen(false)} />
          <aside className="relative h-full w-[280px] border-r border-white/10 bg-surface shadow-2xl">
            {sidebar}
          </aside>
        </div>
      ) : null}

      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-white/[0.06] bg-base/80 px-4 py-3 backdrop-blur-md sm:px-6">
          <button
            type="button"
            className="rounded-lg border border-white/10 p-2 text-muted transition hover:text-ink lg:hidden"
            onClick={() => setMenuOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={17} />
          </button>

          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink">
              {TITLES[location.pathname] ||
                (location.pathname.startsWith('/forensics/')
                  ? 'Audio forensics workspace'
                  : 'VoiceGuard AI')}
            </p>
            <p className="hidden text-[11px] text-muted sm:block">
              Voice cloning detection · CPU inference · SIH problem statement SIH26104
            </p>
          </div>

          <Button size="sm" variant="secondary" onClick={() => navigate('/upload')} className="hidden sm:inline-flex">
            <Upload size={14} /> New analysis
          </Button>

          <button
            type="button"
            onClick={() => navigate('/profile')}
            className="flex h-9 w-9 items-center justify-center rounded-xl border border-accent/25 bg-accent/10 text-xs font-semibold text-accent transition hover:bg-accent/15"
            aria-label="Open profile"
            title={user?.email}
          >
            {initials}
          </button>
        </header>

        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>

        <footer className="border-t border-white/[0.05] px-4 py-4 text-center text-[11px] text-muted sm:px-6">
          AI voice detection is not 100% reliable. Results are indicators, not conclusive evidence.
        </footer>
      </div>
    </div>
  )
}
