'use client'

import { useEffect, useState } from 'react'
import { NavHeader } from '@/components/NavHeader'
import { TradeTable } from '@/components/TradeTable'
import { TradeDetailDrawer } from '@/components/TradeDetailDrawer'
import { fetchTrades, type Trade } from '@/lib/api'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function TradesPage() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null)

  // Filters
  const [underlying, setUnderlying] = useState('')
  const [status, setStatus] = useState<'open' | 'closed' | ''>('')
  const [strategy, setStrategy] = useState('')
  const [strategies, setStrategies] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const pageSize = 25

  // Load strategies list
  useEffect(() => {
    async function loadStrategies() {
      try {
        const res = await fetch(`${API_URL}/api/trades/strategies`)
        if (res.ok) {
          const data = await res.json()
          setStrategies(data)
        }
      } catch (err) {
        console.error('Failed to load strategies', err)
      }
    }
    loadStrategies()
  }, [])

  const loadTrades = async () => {
    setLoading(true)
    try {
      const data = await fetchTrades({
        underlying: underlying || undefined,
        strategy: strategy || undefined,
        status: status || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page,
        page_size: pageSize,
      })
      setTrades(data.trades)
      setTotal(data.total)
    } catch (err) {
      setError('Failed to load trades')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTrades()
  }, [underlying, strategy, status, dateFrom, dateTo, page])

  const handleTradeDeleted = (tradeId: string) => {
    // Remove from local state and refresh
    setTrades(trades.filter(t => t.id !== tradeId))
    setTotal(t => t - 1)
  }

  const totalPages = Math.ceil(total / pageSize)

  const handleExportCSV = () => {
    // Build CSV content
    const headers = ['Underlying', 'Strategy', 'Open Date', 'Expiration', 'DTE', 'Open $', 'Close $', 'Fees', 'P&L Net', 'Status']
    const rows = trades.map((t) => [
      t.underlying,
      t.strategy,
      t.open_time,
      t.expiration || '',
      t.dte_at_entry ?? '',
      t.open_amount,
      t.close_amount,
      t.total_fees,
      t.realized_pnl_net,
      t.is_closed ? (t.is_expired ? 'Expired' : 'Closed') : 'Open',
    ])

    const csv = [headers, ...rows].map((row) => row.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `trades-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <NavHeader />

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6 flex flex-wrap items-center gap-4">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Trade Log
          </h2>
          <div className="flex flex-1 flex-wrap justify-end gap-3">
            <input
              type="text"
              placeholder="Filter by ticker..."
              value={underlying}
              onChange={(e) => {
                setUnderlying(e.target.value.toUpperCase())
                setPage(1)
              }}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
            <select
              value={strategy}
              onChange={(e) => {
                setStrategy(e.target.value)
                setPage(1)
              }}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            >
              <option value="">All Strategies</option>
              {strategies.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value as 'open' | 'closed' | '')
                setPage(1)
              }}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            >
              <option value="">All Status</option>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
            </select>
            <div className="flex items-center gap-1">
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => {
                  setDateFrom(e.target.value)
                  setPage(1)
                }}
                className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                title="From date"
              />
              <span className="text-zinc-400">-</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => {
                  setDateTo(e.target.value)
                  setPage(1)
                }}
                className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                title="To date"
              />
            </div>
            <button
              onClick={handleExportCSV}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            >
              Export CSV
            </button>
          </div>
        </div>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
            {error}
          </div>
        ) : loading ? (
          <div className="py-8 text-center text-zinc-500">Loading...</div>
        ) : (
          <>
            <TradeTable trades={trades} onTradeClick={setSelectedTrade} />

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-4 flex items-center justify-between">
                <p className="text-sm text-zinc-500">
                  Showing {(page - 1) * pageSize + 1} to{' '}
                  {Math.min(page * pageSize, total)} of {total} trades
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-50 dark:border-zinc-700"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-50 dark:border-zinc-700"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      <TradeDetailDrawer
        trade={selectedTrade}
        onClose={() => setSelectedTrade(null)}
        onDelete={handleTradeDeleted}
      />
    </div>
  )
}
