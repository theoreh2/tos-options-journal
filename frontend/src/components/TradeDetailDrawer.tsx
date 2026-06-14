'use client'

import { useEffect, useState } from 'react'
import type { Trade } from '@/lib/api'

interface TradeDetailDrawerProps {
  trade: Trade | null
  onClose: () => void
  onNotesUpdate?: (tradeId: string, notes: string) => void
}

interface TradeDetail extends Trade {
  notes?: string
  cash_events?: Array<{
    id: string
    event_type: string
    event_date: string
    direction: string
    qty: number
    strikes: number[]
    option_type: string
    amount: number
    misc_fees: number
    commissions: number
    description: string
  }>
  legs?: Array<{
    id: string
    side: string
    qty: number
    strike: number
    option_type: string
    expiration: string
    price: number
  }>
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export function TradeDetailDrawer({ trade, onClose, onNotesUpdate }: TradeDetailDrawerProps) {
  const [detail, setDetail] = useState<TradeDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [notes, setNotes] = useState('')
  const [savingNotes, setSavingNotes] = useState(false)

  useEffect(() => {
    if (!trade) {
      setDetail(null)
      return
    }

    async function fetchDetail() {
      if (!trade) return
      setLoading(true)
      try {
        const res = await fetch(`${API_URL}/api/trades/${trade.id}`)
        if (res.ok) {
          const data = await res.json()
          setDetail(data)
          setNotes(data.notes || '')
        }
      } catch (err) {
        console.error('Failed to fetch trade detail', err)
      } finally {
        setLoading(false)
      }
    }

    fetchDetail()
  }, [trade])

  const handleSaveNotes = async () => {
    if (!trade) return
    setSavingNotes(true)
    try {
      const res = await fetch(`${API_URL}/api/trades/${trade.id}/notes?notes=${encodeURIComponent(notes)}`, {
        method: 'PUT',
      })
      if (res.ok && onNotesUpdate) {
        onNotesUpdate(trade.id, notes)
      }
    } catch (err) {
      console.error('Failed to save notes', err)
    } finally {
      setSavingNotes(false)
    }
  }

  if (!trade) return null

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(value)
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  }

  const formatDateTime = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    })
  }

  const pnlClass = trade.realized_pnl_net >= 0 ? 'text-green-600' : 'text-red-600'

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50 transition-opacity"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed right-0 top-0 z-50 h-full w-full max-w-lg overflow-y-auto bg-white shadow-xl dark:bg-zinc-900">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-4 dark:border-zinc-800 dark:bg-zinc-900">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {trade.underlying}
            </h2>
            <p className="text-sm text-zinc-500">
              {trade.strategy.replace(/_/g, ' ')}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-2 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {loading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="text-zinc-500">Loading...</div>
          </div>
        ) : (
          <div className="p-6">
            {/* Summary */}
            <div className="mb-6 grid grid-cols-2 gap-4">
              <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
                <p className="text-sm text-zinc-500">Status</p>
                <p className="mt-1 font-medium text-zinc-900 dark:text-zinc-100">
                  {trade.is_closed ? (trade.is_expired ? 'Expired' : 'Closed') : 'Open'}
                </p>
              </div>
              <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
                <p className="text-sm text-zinc-500">Net P&L</p>
                <p className={`mt-1 font-medium ${pnlClass}`}>
                  {trade.is_closed ? formatCurrency(trade.realized_pnl_net) : '-'}
                </p>
              </div>
              <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
                <p className="text-sm text-zinc-500">Open Amount</p>
                <p className="mt-1 font-medium text-zinc-900 dark:text-zinc-100">
                  {formatCurrency(trade.open_amount)}
                </p>
              </div>
              <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
                <p className="text-sm text-zinc-500">Close Amount</p>
                <p className="mt-1 font-medium text-zinc-900 dark:text-zinc-100">
                  {trade.is_closed ? formatCurrency(trade.close_amount) : '-'}
                </p>
              </div>
              <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
                <p className="text-sm text-zinc-500">Total Fees</p>
                <p className="mt-1 font-medium text-zinc-900 dark:text-zinc-100">
                  {formatCurrency(trade.total_fees)}
                </p>
              </div>
              <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
                <p className="text-sm text-zinc-500">DTE at Entry</p>
                <p className="mt-1 font-medium text-zinc-900 dark:text-zinc-100">
                  {trade.dte_at_entry ?? '-'}
                </p>
              </div>
            </div>

            {/* Dates */}
            <div className="mb-6">
              <h3 className="mb-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">Timeline</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-zinc-500">Opened</span>
                  <span className="text-zinc-900 dark:text-zinc-100">{formatDateTime(trade.open_time)}</span>
                </div>
                {trade.close_time && (
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Closed</span>
                    <span className="text-zinc-900 dark:text-zinc-100">{formatDateTime(trade.close_time)}</span>
                  </div>
                )}
                {trade.expiration && (
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Expiration</span>
                    <span className="text-zinc-900 dark:text-zinc-100">{formatDate(trade.expiration)}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Cash Events */}
            {detail?.cash_events && detail.cash_events.length > 0 && (
              <div className="mb-6">
                <h3 className="mb-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  Cash Events ({detail.cash_events.length})
                </h3>
                <div className="space-y-2">
                  {detail.cash_events.map((event) => (
                    <div
                      key={event.id}
                      className="rounded-lg border border-zinc-200 p-3 text-sm dark:border-zinc-800"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-zinc-900 dark:text-zinc-100">
                          {event.event_type}
                        </span>
                        <span className={event.amount >= 0 ? 'text-green-600' : 'text-red-600'}>
                          {formatCurrency(event.amount)}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-zinc-500 truncate" title={event.description}>
                        {event.description}
                      </p>
                      {(event.misc_fees !== 0 || event.commissions !== 0) && (
                        <p className="mt-1 text-xs text-zinc-400">
                          Fees: {formatCurrency(Math.abs(event.misc_fees) + Math.abs(event.commissions))}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Notes */}
            <div className="mb-6">
              <h3 className="mb-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">Notes</h3>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Add notes about this trade..."
                rows={4}
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
              />
              <button
                onClick={handleSaveNotes}
                disabled={savingNotes}
                className="mt-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {savingNotes ? 'Saving...' : 'Save Notes'}
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
