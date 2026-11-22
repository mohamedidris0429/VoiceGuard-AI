import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LogOut, Lock, Save, Settings, User } from 'lucide-react'
import { authApi } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import {
  Alert,
  Button,
  Card,
  Field,
  PageHeader,
  Toggle,
} from '../components/ui'
import { formatDate } from '../utils/format'

export default function ProfilePage() {
  const { user, updateUser, logout } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()

  const [name, setName] = useState(user?.name || '')
  const [preferences, setPreferences] = useState({
    email_notifications: false,
    default_view: 'dashboard',
    compact_tables: false,
  })
  const [profileError, setProfileError] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)

  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' })
  const [passwordErrors, setPasswordErrors] = useState({})
  const [passwordError, setPasswordError] = useState('')
  const [savingPassword, setSavingPassword] = useState(false)

  useEffect(() => {
    if (user) {
      setName(user.name)
      setPreferences((current) => ({ ...current, ...(user.preferences || {}) }))
    }
  }, [user])

  const saveProfile = async (event) => {
    event.preventDefault()
    setProfileError('')
    if (name.trim().length < 2) {
      setProfileError('Enter your name (at least 2 characters).')
      return
    }
    setSavingProfile(true)
    try {
      const updated = await authApi.updateProfile({ name: name.trim(), preferences })
      updateUser(updated)
      toast.success('Profile updated.')
    } catch (err) {
      setProfileError(err.message)
    } finally {
      setSavingProfile(false)
    }
  }

  const savePassword = async (event) => {
    event.preventDefault()
    const errors = {}
    if (!passwords.current) errors.current = 'Enter your current password.'
    if (passwords.next.length < 8) errors.next = 'New password must be at least 8 characters.'
    else if (!/[A-Za-z]/.test(passwords.next) || !/\d/.test(passwords.next)) {
      errors.next = 'New password needs a letter and a number.'
    }
    if (passwords.confirm !== passwords.next) errors.confirm = 'Passwords do not match.'
    setPasswordErrors(errors)
    if (Object.keys(errors).length > 0) return

    setSavingPassword(true)
    setPasswordError('')
    try {
      await authApi.changePassword({
        current_password: passwords.current,
        new_password: passwords.next,
      })
      setPasswords({ current: '', next: '', confirm: '' })
      toast.success('Password changed successfully.')
    } catch (err) {
      setPasswordError(err.message)
    } finally {
      setSavingPassword(false)
    }
  }

  const signOut = () => {
    logout()
    navigate('/login', { replace: true })
  }

  if (!user) return null

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Account"
        title="Profile & settings"
        description="Manage your identity, preferences and credentials."
        actions={
          <Button variant="danger" onClick={signOut}>
            <LogOut size={15} /> Sign out
          </Button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4">
          <Card>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <User size={15} className="text-accent" /> Profile details
            </h2>
            <form onSubmit={saveProfile} className="mt-4 space-y-4" noValidate>
              <Field label="Full name" htmlFor="profile-name" required>
                <input
                  id="profile-name"
                  className="input"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  autoComplete="name"
                />
              </Field>

              <Field
                label="Email address"
                htmlFor="profile-email"
                hint="Email addresses are unique account identifiers and cannot be changed here."
              >
                <input id="profile-email" className="input" value={user.email} disabled readOnly />
              </Field>

              <div className="space-y-2">
                <p className="label mb-0">Preferences</p>
                <Toggle
                  id="email-notifications"
                  label="Email notifications"
                  description="Reserved for future analysis notifications. Stored with your account."
                  checked={preferences.email_notifications}
                  onChange={(value) =>
                    setPreferences((current) => ({ ...current, email_notifications: value }))
                  }
                />
                <Toggle
                  id="compact-tables"
                  label="Compact tables"
                  description="Applies a denser row style to the analysis history table."
                  checked={preferences.compact_tables}
                  onChange={(value) =>
                    setPreferences((current) => ({ ...current, compact_tables: value }))
                  }
                />
                <Field label="Default view after sign-in" htmlFor="default-view">
                  <select
                    id="default-view"
                    className="input"
                    value={preferences.default_view}
                    onChange={(event) =>
                      setPreferences((current) => ({ ...current, default_view: event.target.value }))
                    }
                  >
                    <option value="dashboard">Dashboard</option>
                    <option value="history">Analysis history</option>
                    <option value="upload">Analyse audio</option>
                  </select>
                </Field>
              </div>

              {profileError ? <Alert tone="error">{profileError}</Alert> : null}

              <Button type="submit" loading={savingProfile}>
                <Save size={15} /> Save profile
              </Button>
            </form>
          </Card>

          <Card>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Lock size={15} className="text-teal" /> Change password
            </h2>
            <p className="mt-0.5 text-xs text-muted">
              Passwords are hashed with bcrypt. Changing it does not sign out other sessions until
              their token expires.
            </p>
            <form onSubmit={savePassword} className="mt-4 space-y-4" noValidate>
              <Field label="Current password" htmlFor="current-password" error={passwordErrors.current} required>
                <input
                  id="current-password"
                  type="password"
                  className="input"
                  autoComplete="current-password"
                  value={passwords.current}
                  onChange={(event) =>
                    setPasswords((current) => ({ ...current, current: event.target.value }))
                  }
                />
              </Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="New password" htmlFor="new-password" error={passwordErrors.next} required>
                  <input
                    id="new-password"
                    type="password"
                    className="input"
                    autoComplete="new-password"
                    value={passwords.next}
                    onChange={(event) =>
                      setPasswords((current) => ({ ...current, next: event.target.value }))
                    }
                  />
                </Field>
                <Field label="Confirm new password" htmlFor="confirm-password" error={passwordErrors.confirm} required>
                  <input
                    id="confirm-password"
                    type="password"
                    className="input"
                    autoComplete="new-password"
                    value={passwords.confirm}
                    onChange={(event) =>
                      setPasswords((current) => ({ ...current, confirm: event.target.value }))
                    }
                  />
                </Field>
              </div>

              {passwordError ? <Alert tone="error">{passwordError}</Alert> : null}

              <Button type="submit" variant="teal" loading={savingPassword}>
                <Lock size={15} /> Update password
              </Button>
            </form>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Settings size={15} className="text-muted" /> Account
            </h2>
            <dl className="mt-3 space-y-3 text-[13px]">
              {[
                ['Account ID', `#${user.id}`],
                ['Name', user.name],
                ['Email', user.email],
                ['Member since', formatDate(user.created_at)],
              ].map(([label, value]) => (
                <div key={label} className="flex items-start justify-between gap-3">
                  <dt className="text-muted">{label}</dt>
                  <dd className="max-w-[60%] truncate text-right font-medium text-ink" title={String(value)}>
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card className="border-warn/20 bg-warn/[0.03]">
            <h2 className="text-sm font-semibold text-warn">Data & privacy</h2>
            <p className="mt-2 text-[12px] leading-relaxed text-muted">
              Uploaded recordings are stored privately against your account. Analyses are scoped to
              you: other accounts receive “not found” for your records. Delete an analysis from its
              detail page or the history table to remove the audio file permanently.
            </p>
          </Card>
        </div>
      </div>
    </div>
  )
}
