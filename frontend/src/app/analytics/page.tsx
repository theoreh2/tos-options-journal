'use client'

import { useEffect, useState } from 'react'
import { NavHeader } from '@/components/NavHeader'
import { PnLCard } from '@/components/PnLCard'
import {
  StrategyPnLChart,
  UnderlyingPnLChart,
  PnLOverTimeChart,
  FeeAnalysisChart,
} from '@/components/AnalyticsCharts'
import {
  fetchAnalyticsSummary,
  fetchAnalyticsByStrategy,
  fetchAnalyticsByUnderlying,
  fetchPnLOverTime,
  type AnalyticsSummary,
  type StrategyBreakdown,
  type UnderlyingBreakdown,
  type PnLOverTimePoint,
} from '@/lib/api'

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [byStrategy, setByStrategy] = useState<StrategyBreakdown[]>([])
  const [byUnderlying, setByUnderlying] = useState<UnderlyingBreakdown[]>([])
  const [pnlOverTime, setPnlOverTime] = useState<PnLOverTimePoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadData() {
      try {
        const [summaryData, strategyData, underlyingData, timeData] = await Promise.all([
          fetchAnalyticsSummary(),
          fetchAnalyticsByStrategy(),
          fetchAnalyticsByUnderlying(),
          fetchPnLOverTime(),
        ])
        setSummary(summaryData)
        setByStrategy(strategyData)
        setByUnderlying(underlyingData)
        setPnlOverTime(timeData)
      } catch (err) {
        setError('Failed to load analytics')
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
        <h2 className="mb-6 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Analytics
        </h2>

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
                subtitle={`${summary?.total_pnl_gross ? ((summary.total_fees / summary.total_pnl_gross) * 100).toFixed(1) : 0}% of gross`}
              />
              <PnLCard
                title="Win Rate"
                value={summary?.win_rate ?? 0}
                isPercentage
                isCurrency={false}
                subtitle={`${summary?.win_count ?? 0}W / ${summary?.loss_count ?? 0}L`}
              />
            </div>

            {/* Avg Winner / Loser */}
            <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <PnLCard
                title="Avg Winner"
                value={summary?.avg_winner ?? 0}
              />
              <PnLCard
                title="Avg Loser"
                value={summary?.avg_loser ?? 0}
              />
              <PnLCard
                title="Open Positions"
                value={summary?.open_trades ?? 0}
                isCurrency={false}
              />
              <PnLCard
                title="Total Trades"
                value={summary?.total_trades ?? 0}
                isCurrency={false}
              />
            </div>

            {/* Charts */}
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
                <h3 className="mb-4 font-medium text-zinc-900 dark:text-zinc-100">
                  P&L by Strategy
                </h3>
                <StrategyPnLChart data={byStrategy} />
              </div>
              <div className="rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
                <h3 className="mb-4 font-medium text-zinc-900 dark:text-zinc-100">
                  P&L by Underlying (Top 10)
                </h3>
                <UnderlyingPnLChart data={byUnderlying} />
              </div>
              <div className="rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
                <h3 className="mb-4 font-medium text-zinc-900 dark:text-zinc-100">
                  Cumulative P&L Over Time
                </h3>
                <PnLOverTimeChart data={pnlOverTime} />
              </div>
              <div className="rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
                <h3 className="mb-4 font-medium text-zinc-900 dark:text-zinc-100">
                  Fee Drag Analysis
                </h3>
                <FeeAnalysisChart
                  data={pnlOverTime}
                  totalFees={summary?.total_fees ?? 0}
                  totalPnlGross={summary?.total_pnl_gross ?? 0}
                />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
