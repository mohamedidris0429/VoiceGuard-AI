import {
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  FileAudio,
  Filter,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Modal,
  PageHeader,
  Skeleton,
} from '../components/ui'
import { VerdictBadge } from '../components/verdict'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { audioApi, historyApi, reportsApi } from '../services/api'
import {
  formatDateTime,
  formatDuration,
  formatPercent,
  statusLabel,
  statusTone,
} from '../utils/format'

const DEFAULT_PAGE_SIZE = 10

export default function HistoryPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const compact = Boolean(user?.preferences?.compact_tables)

  // All density styles derived from one source of truth
  const tableFontSize = compact ? 'text-[13px]' : 'text-sm'
  const headPadding = compact ? 'px-3 py-1.5' : 'px-5 py-3'
  const cellPadding = compact ? 'px-2 py-1.5' : 'px-3 py-3'
  const spanInnerPadding = compact ? 'p-1' : 'p-1.5'
  const dataDensity = compact ? 'compact' : 'comfortable'
  const [searchInput, setSearchInput] = useState('')
  const [filters, setFilters] = useState({
    q: '',
    status: '',
    prediction: '',
    sort: 'created_at',
    order: 'desc',
    page: 1,
    page_size: DEFAULT_PAGE_SIZE,
  })
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [downloadingId, setDownloadingId] = useState(null)

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setFilters((current) => ({ ...current, q: searchInput.trim(), page: 1 }))
    }, 350)
    return () => window.clearTimeout(timeout)
  }, [searchInput])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await historyApi.list(filters)
      setData(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    load()
  }, [load])

  const updateFilter = (key, value) =>
    setFilters((current) => ({ ...current, [key]: value, page: 1 }))

  const resetFilters = () => {
    setSearchInput('')
    setFilters({
      q: '',
      status: '',
      prediction: '',
      sort: 'created_at',
      order: 'desc',
      page: 1,
      page_size: DEFAULT_PAGE_SIZE,
    })
  }

  const downloadReport = async (analysis) => {
    setDownloadingId(analysis.id)
    try {
      const { blob, filename } = await reportsApi.download(analysis.id)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      setTimeout(() => URL.revokeObjectURL(url), 4000)
      toast.success('PDF report downloaded.')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setDownloadingId(null)
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await audioApi.remove(deleteTarget.id)
      toast.success('Analysis deleted.')
      setDeleteTarget(null)
      if (data && data.items.length === 1 && filters.page > 1) {
        setFilters((current) => ({ ...current, page: current.page - 1 }))
      } else {
        load()
      }
    } catch (err) {
      toast.error(err.message)
    } finally {
      setDeleting(false)
    }
  }

  const hasFilters = Boolean(filters.q || filters.status || filters.prediction)
  const items = data?.items || []

  const tableClass = compact ? 'w-full min-w-[760px] text-[13px]' : 'w-full min-w-[760px] text-sm'
  const headClass = compact ? 'px-3 py-1.5' : 'px-5 py-3'
  const cellClass = compact ? 'px-2 py-1.5' : 'px-3 py-3'
  const spanClass = compact ? 'p-1' : 'p-1.5'

  const spanClasses = `rounded-lg border border-white/10 bg-white/3 text-muted ${spanClass}`

  // Class names for table cells (template strings keep Tailwind's brackets intact).
  const monoCellClass = `mono ${cellPadding} text-[12px] text-muted`
  const dateCellClass = `${cellPadding} text-[12px] text-muted`

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Audit trail"
        title="Analysis history"
        description="Every analysis stored against your account. Only you can view, download or delete these records."
        actions={
          <Button onClick={() => navigate('/upload')}>
            <Upload size={15} /> New analysis
          </Button>
        }
      />

      <Card className="mb-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              className="input pl-10"
              placeholder="Search by filename…"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              aria-label="Search analyses by filename"
            />
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <select
              className="input"
              value={filters.status}
              onChange={(event) => updateFilter('status', event.target.value)}
              aria-label="Filter by status"
            >
              <option value="">All statuses</option>
              <option value="completed">Completed</option>
              <option value="pending">Pending</option>
              <option value="unavailable">Unavailable</option>
              <option value="failed">Failed</option>
            </select>

            <select
              className="input"
              value={filters.prediction}
              onChange={(event) => updateFilter('prediction', event.target.value)}
              aria-label="Filter by classification"
            >
              <option value="">All results</option>
              <option value="genuine">Genuine</option>
              <option value="synthetic">Synthetic</option>
            </select>

            <select
              className="input"
              value={`${filters.sort}:${filters.order}`}
              onChange={(event) => {
                const [sort, order] = event.target.value.split(':')
                setFilters((current) => ({ ...current, sort, order, page: 1 }))
              }}
              aria-label="Sort analyses"
            >
              <option value="created_at:desc">Newest first</option>
              <option value="created_at:asc">Oldest first</option>
              <option value="filename:asc">Filename A–Z</option>
              <option value="filename:desc">Filename Z–A</option>
              <option value="model_score:desc">Highest score</option>
              <option value="audio_duration:desc">Longest audio</option>
            </select>

            <Button variant="ghost" onClick={resetFilters} disabled={!hasFilters && !searchInput}>
              <Filter size={14} /> Reset
            </Button>
          </div>
        </div>
      </Card>

      {error ? (
        <Alert
          tone="error"
          className="mb-4"
          title="Could not load your history"
          action={
            <Button size="sm" variant="secondary" onClick={load}>
              <RefreshCw size={13} /> Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}

      <Card className="overflow-hidden p-0">
        {loading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-12" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={FileAudio}
            title={hasFilters ? 'No analyses match these filters' : 'No analyses yet'}
            description={
              hasFilters
                ? 'Try a different filename, status or classification.'
                : 'Upload a recording or capture one with your microphone to build your history.'
            }
            action={
              hasFilters ? (
                <Button variant="secondary" size="sm" onClick={resetFilters}>
                  Clear filters
                </Button>
              ) : (
                <Button size="sm" onClick={() => navigate('/upload')}>
                  <Upload size={14} /> Analyse a recording
                </Button>
              )
            }
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className={tableClass} data-density={dataDensity}>
                <thead>
                  <tr>
                    <th className={headPadding}>Recording</th>
                    <th className={headPadding}>Result</th>
                    <th className={headPadding}>Score</th>
                    <th className={headPadding}>Duration</th>
                    <th className={headPadding}>Analysed</th>
                    <th className={`${headPadding} text-right`}>Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/2">
                  {items.map((item) => (
                    <tr key={item.id} className="transition hover:bg-white/2">
                      <td className={headPadding}>
                        <div className="flex items-center gap-2.5">
                          <span
                            className={spanClasses}
                          >
                            <FileAudio size={14} aria-hidden />
                          </span>
                          <div className="min-w-0">
                            <Link
                              to={`/analysis/${item.id}`}
                              className="block max-w-[220px] truncate font-medium text-ink hover:text-accent"
                              title={item.filename}
                            >
                              {item.filename}
                            </Link>
                            <p className="text-[11px] text-muted">
                              # {item.id} · {(item.file_format || '').toUpperCase()}
                              {item.source === 'recording' ? ' · microphone' : ''}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className={cellPadding}>
                        <div className="flex flex-col items-start gap-1">
                          <VerdictBadge prediction={item.predicted_class} status={item.analysis_status} />
                          {item.analysis_status !== 'completed' ? (
                            <Badge tone={statusTone(item.analysis_status)}>
                              {statusLabel(item.analysis_status)}
                            </Badge>
                          ) : null}
                        </div>
                      </td>
                      <td className={monoCellClass}>
                        {item.model_score != null ? formatPercent(item.model_score) : '—'}
                      </td>
                      <td className={monoCellClass}>
                        {formatDuration(item.audio_duration)}
                      </td>
                      <td className={dateCellClass}>{formatDateTime(item.created_at)}</td>
                      <td className={headPadding}>
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => navigate(`/analysis/${item.id}`)}
                            aria-label={`View analysis ${item.id}`}
                            title="View details"
                          >
                            <Eye size={14} />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => downloadReport(item)}
                            disabled={item.analysis_status !== 'completed'}
                            aria-label={`Download report for analysis ${item.id}`}
                            title="Download PDF report"
                          >
                            {downloadingId === item.id ? (
                              <Loader2 size={14} className="animate-spin" />
                            ) : (
                              <Download size={14} />
                            )}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteTarget(item)}
                            aria-label="Delete analysis"
                            title="Delete"
                            className="hover:text-danger"
                          >
                            <Trash2 size={14} />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/6 px-5 py-3">
              <p className="text-[12px] text-muted">
                Showing {(data.page - 1) * data.page_size + 1}–{Math.min(data.page * data.page_size, data.total)} of {data.total}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={data.page <= 1}
                  onClick={() => setFilters((current) => ({ ...current, page: current.page - 1 }))}
                >
                  <ChevronLeft size={14} /> Previous
                </Button>
                <span className="mono text-[12px] text-muted">
                  {data.page} / {data.pages}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={data.page >= data.pages}
                  onClick={() => setFilters((current) => ({ ...current, page: current.page + 1 }))}
                >
                  Next <ChevronRight size={14} />
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>

      <Modal
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        title="Delete this analysis?"
        description="This permanently removes the stored audio file and its result."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="danger" onClick={confirmDelete} loading={deleting}>
              <Trash2 size={14} /> Delete
            </Button>
          </>
        }
      >
        {deleteTarget ? (
          <p className="text-[13px] text-muted">
            <span className="font-medium text-ink">{deleteTarget.filename}</span> ·
            {formatDateTime(deleteTarget.created_at)}
          </p>
        ) : null}
      </Modal>
    </div>
  )
}