import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { BarChart3 } from 'lucide-react'
import { EmptyState } from './ui'

const AXIS = { stroke: '#64748B', fontSize: 11 }
const GRID = '#1E2D45'

function ChartTooltip({ active, payload, label, suffix = '' }) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="rounded-lg border border-white/10 bg-[#0B1524] px-3 py-2 text-xs shadow-xl">
      <p className="mb-1 font-semibold text-ink">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey || entry.name} className="text-muted">
          <span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: entry.color }} />
          {entry.name}: <span className="font-semibold text-ink">{entry.value}{suffix}</span>
        </p>
      ))}
    </div>
  )
}

export function ChartCard({ title, description, children, className, action }) {
  return (
    <div className={`card p-5 ${className || ''}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {description ? <p className="mt-0.5 text-xs text-muted">{description}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

const EMPTY_CHART = (
  <EmptyState
    icon={BarChart3}
    title="No data yet"
    description="Charts populate automatically after your first completed analysis."
    className="py-10"
  />
)

export function TrendChart({ data = [] }) {
  const hasData = data.some((point) => point.total > 0)
  if (!hasData) return EMPTY_CHART
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 6, left: -18, bottom: 0 }}>
          <defs>
            <linearGradient id="genuineFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22C55E" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#22C55E" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="syntheticFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#EF4444" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#EF4444" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="date"
            tick={AXIS}
            tickLine={false}
            axisLine={{ stroke: GRID }}
            tickFormatter={(value) => value.slice(5)}
          />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} width={40} />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: '#334155' }} />
          <Legend wrapperStyle={{ fontSize: 11, color: '#94A3B8' }} iconType="circle" iconSize={7} />
          <Area
            type="monotone"
            dataKey="genuine"
            name="Genuine"
            stroke="#22C55E"
            strokeWidth={2}
            fill="url(#genuineFill)"
          />
          <Area
            type="monotone"
            dataKey="synthetic"
            name="Synthetic"
            stroke="#EF4444"
            strokeWidth={2}
            fill="url(#syntheticFill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

const PIE_COLORS = ['#22C55E', '#EF4444', '#F59E0B']

export function DistributionChart({ genuine = 0, synthetic = 0, unavailable = 0 }) {
  const data = [
    { name: 'Genuine', value: genuine },
    { name: 'Synthetic', value: synthetic },
    { name: 'Unavailable', value: unavailable },
  ].filter((entry) => entry.value > 0)

  if (data.length === 0) return EMPTY_CHART

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={54}
            outerRadius={82}
            paddingAngle={3}
            stroke="none"
          >
            {data.map((entry, index) => (
              <Cell key={entry.name} fill={PIE_COLORS[index % PIE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip />} />
          <Legend wrapperStyle={{ fontSize: 11, color: '#94A3B8' }} iconType="circle" iconSize={7} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ConfidenceChart({ buckets = [] }) {
  const hasData = buckets.some((bucket) => bucket.count > 0)
  if (!hasData) return EMPTY_CHART
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={buckets} margin={{ top: 4, right: 6, left: -20, bottom: 0 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} width={40} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
          <Bar dataKey="count" name="Analyses" radius={[6, 6, 0, 0]} fill="#14B8A6" maxBarSize={46} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function DurationChart({ buckets = [] }) {
  const hasData = buckets.some((bucket) => bucket.count > 0)
  if (!hasData) return EMPTY_CHART
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={buckets} margin={{ top: 4, right: 6, left: -20, bottom: 0 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} width={40} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
          <Bar dataKey="count" name="Analyses" radius={[6, 6, 0, 0]} fill="#22C55E" maxBarSize={46} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
