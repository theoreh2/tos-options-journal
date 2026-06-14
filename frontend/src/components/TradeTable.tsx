'use client'

import type { Trade } from '@/lib/api'

interface TradeTableProps {
  trades: Trade[]
  onTradeClick?: (trade: Trade) => void
}

export function TradeTable({ trades, onTradeClick }: TradeTableProps) {
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
      year: '2-digit',
    })
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
      <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-800">
        <thead className="bg-zinc-50 dark:bg-zinc-900">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
              Underlying
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
              Strategy
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
              Open
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
              Exp
            </th>
            <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-zinc-500">
              DTE
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-zinc-500">
              Open $
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-zinc-500">
              Close $
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-zinc-500">
              Fees
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-zinc-500">
              P&L Net
            </th>
            <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-zinc-500">
              Status
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-800 dark:bg-zinc-950">
          {trades.length === 0 ? (
            <tr>
              <td colSpan={10} className="px-4 py-8 text-center text-zinc-500">
                No trades found. Import a TOS CSV to get started.
              </td>
            </tr>
          ) : (
            trades.map((trade) => {
              const pnlClass = trade.realized_pnl_net >= 0 ? 'text-green-600' : 'text-red-600'
              return (
                <tr
                  key={trade.id}
                  onClick={() => onTradeClick?.(trade)}
                  className={`${onTradeClick ? 'cursor-pointer' : ''} hover:bg-zinc-50 dark:hover:bg-zinc-900`}
                >
                  <td className="whitespace-nowrap px-4 py-3 font-medium text-zinc-900 dark:text-zinc-100">
                    {trade.underlying}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    {trade.strategy.replace(/_/g, ' ')}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    {formatDate(trade.open_time)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    {trade.expiration ? formatDate(trade.expiration) : '-'}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-center text-zinc-600 dark:text-zinc-400">
                    {trade.dte_at_entry ?? '-'}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right text-zinc-600 dark:text-zinc-400">
                    {formatCurrency(trade.open_amount)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right text-zinc-600 dark:text-zinc-400">
                    {trade.is_closed ? formatCurrency(trade.close_amount) : '-'}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right text-zinc-500">
                    {formatCurrency(trade.total_fees)}
                  </td>
                  <td className={`whitespace-nowrap px-4 py-3 text-right font-medium ${pnlClass}`}>
                    {trade.is_closed ? formatCurrency(trade.realized_pnl_net) : '-'}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-center">
                    <span
                      className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${
                        trade.is_closed
                          ? trade.is_expired
                            ? 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200'
                            : 'bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200'
                          : 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                      }`}
                    >
                      {trade.is_closed ? (trade.is_expired ? 'Expired' : 'Closed') : 'Open'}
                    </span>
                  </td>
                </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
