import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { authApi, getToken, setToken } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [initialising, setInitialising] = useState(Boolean(getToken()))

  useEffect(() => {
    let active = true
    if (!getToken()) {
      setInitialising(false)
      return undefined
    }
    authApi
      .me()
      .then((profile) => {
        if (active) setUser(profile)
      })
      .catch(() => {
        setToken(null)
      })
      .finally(() => {
        if (active) setInitialising(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const handleUnauthorized = () => setUser(null)
    window.addEventListener('voiceguard:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('voiceguard:unauthorized', handleUnauthorized)
  }, [])

  const login = useCallback(async (email, password) => {
    const data = await authApi.login(email, password)
    setToken(data.access_token)
    setUser(data.user)
    return data.user
  }, [])

  const register = useCallback(async (payload) => {
    const data = await authApi.register(payload)
    setToken(data.access_token)
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  const updateUser = useCallback((profile) => setUser(profile), [])

  const value = useMemo(
    () => ({ user, initialising, login, register, logout, updateUser, isAuthenticated: Boolean(user) }),
    [user, initialising, login, register, logout, updateUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
