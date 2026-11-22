import { Outlet } from 'react-router-dom'
import { Activity, Cpu, FileAudio, ShieldCheck, ShieldAlert } from 'lucide-react'

const HIGHLIGHTS = [
  { icon: Cpu, title: 'Real model, CPU inference', text: 'A pretrained wav2vec 2.0 spoof detector runs locally — no GPU required.' },
  { icon: ShieldAlert, title: 'Honest about uncertainty', text: 'Every result is a probability with a documented threshold and model version.' },
  { icon: FileAudio, title: 'Evidence you can keep', text: 'Waveforms, spectrograms, metadata and signed-off PDF reports.' },
]

export default function AuthLayout() {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[1.05fr_0.95fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden border-r border-white/[0.06] bg-surface/30 p-10 lg:flex">
        <div className="pointer-events-none absolute -left-24 top-10 h-80 w-80 rounded-full bg-teal/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 right-0 h-80 w-80 rounded-full bg-accent/10 blur-3xl" />

        <div className="relative flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl border border-accent/30 bg-accent/10 text-accent">
            <ShieldCheck size={22} aria-hidden />
          </span>
          <div>
            <p className="text-base font-semibold tracking-tight text-ink">VoiceGuard AI</p>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">
              SIH26104 · Voice spoof detection
            </p>
          </div>
        </div>

        <div className="relative max-w-lg space-y-6">
          <div className="space-y-3">
            <p className="inline-flex items-center gap-2 rounded-full border border-accent/25 bg-accent/[0.07] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-accent">
              <Activity size={12} /> Detection platform
            </p>
            <h1 className="text-3xl font-semibold leading-tight tracking-tight text-ink">
              Real-time detection and prevention of voice cloning impersonation attacks.
            </h1>
            <p className="text-sm leading-relaxed text-muted">
              Upload a recording or capture one with your microphone. VoiceGuard AI analyses the
              signal with a pretrained anti-spoofing model and reports a calibrated, explained
              estimate — never a guess.
            </p>
          </div>

          <ul className="space-y-3">
            {HIGHLIGHTS.map((item) => (
              <li key={item.title} className="flex gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
                <span className="mt-0.5 rounded-lg border border-accent/20 bg-accent/10 p-1.5 text-accent">
                  <item.icon size={15} aria-hidden />
                </span>
                <div>
                  <p className="text-[13px] font-semibold text-ink">{item.title}</p>
                  <p className="mt-0.5 text-[12px] leading-relaxed text-muted">{item.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative max-w-lg text-[11px] leading-relaxed text-muted">
          AI voice detection is not 100% reliable. Results should be treated as indicators, not
          conclusive evidence of speaker identity.
        </p>
      </section>

      <section className="flex min-h-screen items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent">
              <ShieldCheck size={18} aria-hidden />
            </span>
            <span className="text-sm font-semibold text-ink">VoiceGuard AI</span>
          </div>
          <Outlet />
        </div>
      </section>
    </div>
  )
}
