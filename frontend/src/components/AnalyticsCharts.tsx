'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Cell,
} from 'recharts'
import type { StrategyBreakdown, UnderlyingBreakdown, PnLOverTimePoint } from '@/lib/api'

interface StrategyChartProps {
  data: StrategyBreakdown[]
}

export function StrategyPnLChart({ data }: StrategyChartProps) {
  const chartData = data.map((item) => ({
    name: item.strategy.replace(/_/g, ' '),
    pnl: item.pnl_net,
    trades: item.trade_count,
    winRate: item.trade_count > 0 ? (item.win_count / item.trade_count) * 100 : 0,
  }))

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value)
  }

  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-zinc-500">
        No closed trades yet
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 80, right: 20, top: 10, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis
          type="number"
          tickFormatter={(v) => formatCurrency(v)}
          tick={{ fill: '#71717a', fontSize: 12 }}
        />
        <YAxis
          type="category"
          dataKey="name"
          tick={{ fill: '#71717a', fontSize: 12 }}
          width={75}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#18181b',
            border: '1px solid #27272a',
            borderRadius: '8px',
          }}
          labelStyle={{ color: '#fafafa' }}
          formatter={(value, name) => {
            if (name === 'pnl') return [formatCurrency(value as number), 'P&L']
            return [value, name]
          }}
        />
        <Bar dataKey="pnl" name="pnl" radius={[0, 4, 4, 0]}>
          {chartData.map((entry, index) => (
            <Cell
              key={`cell-${index}`}
              fill={entry.pnl >= 0 ? '#16a34a' : '#dc2626'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

interface UnderlyingChartProps {
  data: UnderlyingBreakdown[]
}

export function UnderlyingPnLChart({ data }: UnderlyingChartProps) {
  // Take top 10 by absolute P&L
  const chartData = [...data]
    .sort((a, b) => Math.abs(b.pnl_net) - Math.abs(a.pnl_net))
    .slice(0, 10)
    .map((item) => ({
      name: item.underlying,
      pnl: item.pnl_net,
      trades: item.trade_count,
    }))

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value)
  }

  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-zinc-500">
        No closed trades yet
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 50, right: 20, top: 10, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis
          type="number"
          tickFormatter={(v) => formatCurrency(v)}
          tick={{ fill: '#71717a', fontSize: 12 }}
        />
        <YAxis
          type="category"
          dataKey="name"
          tick={{ fill: '#71717a', fontSize: 12 }}
          width={45}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#18181b',
            border: '1px solid #27272a',
            borderRadius: '8px',
          }}
          labelStyle={{ color: '#fafafa' }}
          formatter={(value, name) => {
            if (name === 'pnl') return [formatCurrency(value as number), 'P&L']
            return [value, name]
          }}
        />
        <Bar dataKey="pnl" name="pnl" radius={[0, 4, 4, 0]}>
          {chartData.map((entry, index) => (
            <Cell
              key={`cell-${index}`}
              fill={entry.pnl >= 0 ? '#16a34a' : '#dc2626'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

interface PnLOverTimeChartProps {
  data: PnLOverTimePoint[]
}

export function PnLOverTimeChart({ data }: PnLOverTimeChartProps) {
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value)
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    })
  }

  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-zinc-500">
        No closed trades yet
      </div>
    )
  }

  // Determine line color based on final cumulative P&L
  const finalPnL = data.length > 0 ? data[data.length - 1].cumulative_pnl : 0
  const lineColor = finalPnL >= 0 ? '#16a34a' : '#dc2626'

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ left: 20, right: 20, top: 10, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis
          dataKey="date"
          tickFormatter={formatDate}
          tick={{ fill: '#71717a', fontSize: 12 }}
          interval="preserveStartEnd"
        />
        <YAxis
          tickFormatter={(v) => formatCurrency(v)}
          tick={{ fill: '#71717a', fontSize: 12 }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#18181b',
            border: '1px solid #27272a',
            borderRadius: '8px',
          }}
          labelStyle={{ color: '#fafafa' }}
          labelFormatter={(label) => formatDate(String(label))}
          formatter={(value, name) => {
            const label = name === 'cumulative_pnl' ? 'Cumulative P&L' : 'Trade P&L'
            return [formatCurrency(value as number), label]
          }}
        />
        <Line
          type="monotone"
          dataKey="cumulative_pnl"
          stroke={lineColor}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: lineColor }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

interface FeeAnalysisChartProps {
  data: PnLOverTimePoint[]
  totalFees: number
  totalPnlGross: number
}

export function FeeAnalysisChart({ totalFees, totalPnlGross }: FeeAnalysisChartProps) {
  const feePct = totalPnlGross !== 0 ? (Math.abs(totalFees) / Math.abs(totalPnlGross)) * 100 : 0

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-zinc-500">Total Fees Paid</span>
        <span className="font-medium text-zinc-900 dark:text-zinc-100">
          {formatCurrency(Math.abs(totalFees))}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-sm text-zinc-500">Gross P&L</span>
        <span className={`font-medium ${totalPnlGross >= 0 ? 'text-green-600' : 'text-red-600'}`}>
          {formatCurrency(totalPnlGross)}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-sm text-zinc-500">Fee Drag</span>
        <span className="font-medium text-amber-600">
          {feePct.toFixed(1)}% of gross
        </span>
      </div>
      <div className="mt-4">
        <div className="mb-1 flex justify-between text-xs text-zinc-500">
          <span>Fee Impact</span>
          <span>{feePct.toFixed(1)}%</span>
        </div>
        <div className="h-3 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
          <div
            className="h-full rounded-full bg-amber-500"
            style={{ width: `${Math.min(feePct, 100)}%` }}
          />
        </div>
      </div>
    </div>
  )
}
