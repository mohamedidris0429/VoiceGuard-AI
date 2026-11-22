import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react'

const ToastContext = createContext(null)

const TONES = {
  success: { border: 'border-accent/30', text: 'text-accent', Icon: CheckCircle2 },
  error: { border: 'border-danger/30', text: 'text-danger', Icon: AlertTriangle },
  info: { border: 'border-teal/30', text: 'text-teal', Icon: Info },
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const counter = useRef(0)

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const push = useCallback(
    (message, tone = 'success', duration = 4500) => {
      counter.current += 1
      const id = counter.current
      setToasts((current) => [...current, { id, message, tone }])
      window.setTimeout(() => dismiss(id), duration)
    },
    [dismiss],
  )

  const value = useMemo(
    () => ({
      push,
      success: (message) => push(message, 'success'),
      error: (message) => push(message, 'error'),
      info: (message) => push(message, 'info'),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4 sm:inset-x-auto sm:right-5 sm:items-end">
        {toasts.map((toast) => {
          const config = TONES[toast.tone] || TONES.info
          const Icon = config.Icon
          return (
            <div
              key={toast.id}
              role="status"
              className={`pointer-events-auto flex w-full max-w-sm animate-fade-in items-start gap-3 rounded-xl border ${config.border} bg-surface/95 p-3.5 shadow-2xl backdrop-blur`}
            >
              <Icon size={17} className={`mt-0.5 shrink-0 ${config.text}`} aria-hidden />
              <p className="flex-1 text-[13px] leading-relaxed text-ink">{toast.message}</p>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                className="rounded p-0.5 text-muted transition hover:text-ink"
                aria-label="Dismiss notification"
              >
                <X size={14} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside ToastProvider')
  return context
}
