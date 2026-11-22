import { AlertTriangle, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react'
import { Badge, ProgressBar } from './ui'
import { DISCLAIMER, formatPercent, predictionLabel, predictionTone } from '../utils/format'

export function VerdictBadge({ prediction, status }) {
  if (status && status !== 'completed') {
    return (
      <Badge tone={status === 'failed' ? 'danger' : 'warn'}>
        <AlertTriangle size={11} /> {status === 'failed' ? 'Failed' : status === 'unavailable' ? 'Unavailable' : 'Pending'}
      </Badge>
    )
  }
  return <Badge tone={predictionTone(prediction)}>{predictionLabel(prediction)}</Badge>
}

export function ScoreBar({ score, threshold = 0.5, tone }) {
  if (score === null || score === undefined) {
    return <p className="text-xs text-muted">No model score recorded.</p>
  }
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[11px] text-muted">
        <span>Synthetic probability</span>
        <span className="font-semibold text-ink">{formatPercent(score)}</span>
      </div>
      <ProgressBar value={Number(score) * 100} tone={tone || (score >= threshold ? 'danger' : 'accent')} />
      <div className="flex items-center justify-between text-[10px] text-muted">
        <span>0% likely genuine</span>
        <span>Decision threshold {formatPercent(threshold, 0)}</span>
        <span>100% synthetic</span>
      </div>
    </div>
  )
}

export function VerdictPanel({ analysis, showExplanation = true }) {
  const completed = analysis.analysis_status === 'completed'
  const synthetic = analysis.predicted_class === 'synthetic'
  const details = analysis.model_details || {}

  const Icon = completed ? (synthetic ? ShieldAlert : ShieldCheck) : AlertTriangle
  const tone = completed
    ? synthetic
      ? { ring: 'border-danger/40', glow: 'shadow-[0_0_60px_-30px_rgba(239,68,68,0.9)]', text: 'text-danger', bg: 'bg-danger/[0.06]' }
      : { ring: 'border-accent/40', glow: 'shadow-[0_0_60px_-30px_rgba(34,197,94,0.9)]', text: 'text-accent', bg: 'bg-accent/[0.05]' }
    : { ring: 'border-warn/40', glow: '', text: 'text-warn', bg: 'bg-warn/[0.05]' }

  const headline = completed
    ? synthetic
      ? 'Potentially synthetic speech'
      : 'Likely genuine human speech'
    : analysis.analysis_status === 'pending'
      ? 'Analysis pending'
      : 'Unable to analyse'

  const subline = completed
    ? `${formatPercent(analysis.model_score)} probability of synthetic speech · ${formatPercent(
        synthetic ? analysis.model_score : 1 - (analysis.model_score ?? 0),
      )} model confidence`
    : analysis.failure_reason || 'The analysis has not produced a result yet.'

  return (
    <div className={`card ${tone.bg} ${tone.glow} border ${tone.ring} p-5`}>
      <div className="flex items-start gap-3">
        <span className={`rounded-xl border ${tone.ring} ${tone.bg} p-2.5 ${tone.text}`}>
          <Icon size={20} aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className={`text-lg font-semibold tracking-tight ${tone.text}`}>{headline}</h2>
            <VerdictBadge prediction={analysis.predicted_class} status={analysis.analysis_status} />
          </div>
          <p className="mt-1 text-[13px] leading-relaxed text-muted">{subline}</p>
        </div>
      </div>

      {completed ? (
        <div className="mt-5 space-y-4">
          <ScoreBar score={analysis.model_score} threshold={details.threshold ?? 0.5} />
          {showExplanation ? (
            <div className="rounded-xl border border-white/[0.06] bg-[#0B1524]/70 p-3.5">
              <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
                <Sparkles size={12} /> How this score was produced
              </p>
              <p className="mt-2 text-[13px] leading-relaxed text-muted">
                The pretrained detection model processed{' '}
                <span className="font-semibold text-ink">
                  {details.windows_analyzed ?? '—'} × {details.window_seconds ?? 4}s
                </span>{' '}
                windows of this recording and returned a synthetic-speech probability for each
                window. The scores were combined with {details.aggregation || 'a mean aggregate'}.
                Values at or above the {formatPercent(details.threshold ?? 0.5, 0)} threshold are
                classified as potentially synthetic.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}

      <p className="mt-4 flex items-start gap-2 border-t border-white/[0.06] pt-3 text-[11px] leading-relaxed text-muted">
        <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warn" aria-hidden />
        {DISCLAIMER}
      </p>
    </div>
  )
}
