'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { NavHeader } from '@/components/NavHeader'
import { PnLCard } from '@/components/PnLCard'
import { TradeTable } from '@/components/TradeTable'
import { fetchAnalyticsSummary, fetchTrades, type AnalyticsSummary, type Trade } from '@/lib/api'

export default function Dashboard() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [recentTrades, setRecentTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadData() {
      try {
        const [summaryData, tradesData] = await Promise.all([
          fetchAnalyticsSummary(),
          fetchTrades({ page_size: 20 }),
        ])
        setSummary(summaryData)
        setRecentTrades(tradesData.trades)
      } catch (err) {
        setError('Failed to load dashboard data. Is the backend running?')
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
        <NavHeader />
        <div className="flex min-h-[50vh] items-center justify-center">
          <div className="text-zinc-500">Loading...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <NavHeader />

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
            {error}
          </div>
        ) : (
          <>
            {/* Summary Cards */}
            <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <PnLCard
                title="Net P&L"
                value={summary?.total_pnl_net ?? 0}
                subtitle={`${summary?.closed_trades ?? 0} closed trades`}
              />
              <PnLCard
                title="Gross P&L"
                value={summary?.total_pnl_gross ?? 0}
              />
              <PnLCard
                title="Total Fees"
                value={summary?.total_fees ?? 0}
                subtitle="Commissions + exchange fees"
              />
              <PnLCard
                title="Win Rate"
                value={summary?.win_rate ?? 0}
                isPercentage
                isCurrency={false}
                subtitle={`${summary?.win_count ?? 0}W / ${summary?.loss_count ?? 0}L`}
              />
            </div>

            {/* Open Positions */}
            <section className="mb-8">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                  Open Positions ({summary?.open_trades ?? 0})
                </h2>
              </div>
              <TradeTable trades={recentTrades.filter((t) => !t.is_closed)} />
            </section>

            {/* Recent Closed Trades */}
            <section>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                  Recent Closed Trades
                </h2>
                <Link
                  href="/trades"
                  className="text-sm font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400"
                >
                  View all
                </Link>
              </div>
              <TradeTable trades={recentTrades.filter((t) => t.is_closed).slice(0, 5)} />
            </section>
          </>
        )}
      </main>
    </div>
  )
}
