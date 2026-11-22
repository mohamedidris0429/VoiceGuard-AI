import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import AppLayout from './layouts/AppLayout'
import AuthLayout from './layouts/AuthLayout'
import { useAuth } from './context/AuthContext'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import UploadPage from './pages/UploadPage'
import RecordPage from './pages/RecordPage'
import LivePage from './pages/LivePage'
import AnalysisDetail from './pages/AnalysisDetail'
import ForensicsPage from './pages/ForensicsPage'
import HistoryPage from './pages/HistoryPage'
import ComparePage from './pages/ComparePage'
import AnalyticsPage from './pages/AnalyticsPage'
import ProfilePage from './pages/ProfilePage'
import SystemPage from './pages/SystemPage'
import NotFound from './pages/NotFound'

function FullScreenLoader() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 text-muted">
      <span className="flex h-12 w-12 animate-pulse-soft items-center justify-center rounded-2xl border border-accent/30 bg-accent/10 text-accent">
        <ShieldCheck size={22} aria-hidden />
      </span>
      <p className="text-sm">Restoring your secure session…</p>
    </div>
  )
}

function ProtectedRoute() {
  const { isAuthenticated, initialising } = useAuth()
  const location = useLocation()

  if (initialising) return <FullScreenLoader />
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  return <AppLayout />
}

function PublicRoute() {
  const { isAuthenticated, initialising } = useAuth()
  if (initialising) return <FullScreenLoader />
  if (isAuthenticated) return <Navigate to="/dashboard" replace />
  return <AuthLayout />
}

export default function App() {
  return (
    <Routes>
      <Route element={<PublicRoute />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/record" element={<RecordPage />} />
        <Route path="/live" element={<LivePage />} />
        <Route path="/analysis/:analysisId" element={<AnalysisDetail />} />
        <Route path="/forensics/:analysisId" element={<ForensicsPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/system" element={<SystemPage />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
