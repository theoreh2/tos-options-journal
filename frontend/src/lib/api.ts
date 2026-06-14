import { createClient } from './supabase/client'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function getAuthHeaders(): Promise<HeadersInit> {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()

  if (session?.access_token) {
    return {
      'Authorization': `Bearer ${session.access_token}`,
    }
  }
  return {}
}

async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const authHeaders = await getAuthHeaders()
  return fetch(url, {
    ...options,
    headers: {
      ...authHeaders,
      ...options.headers,
    },
  })
}

export interface Trade {
  id: string
  underlying: string
  strategy: string
  spread_label: string | null
  open_time: string
  close_time: string | null
  expiration: string | null
  is_closed: boolean
  is_expired: boolean
  open_amount: number
  close_amount: number
  total_fees: number
  realized_pnl: number
  realized_pnl_net: number
  dte_at_entry: number | null
}

export interface TradeListResponse {
  trades: Trade[]
  total: number
  page: number
  page_size: number
}

export interface AnalyticsSummary {
  total_trades: number
  closed_trades: number
  open_trades: number
  total_pnl_gross: number
  total_pnl_net: number
  total_fees: number
  win_count: number
  loss_count: number
  win_rate: number
  avg_winner: number
  avg_loser: number
}

export interface ImportResult {
  import_id: string
  source: string
  filename: string | null
  date_from: string | null
  date_to: string | null
  raw_events: number
  trades_created: number
  trades_updated: number
  warnings: string[]
}

export async function fetchTrades(params?: {
  underlying?: string
  strategy?: string
  status?: 'open' | 'closed'
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}): Promise<TradeListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.underlying) searchParams.set('underlying', params.underlying)
  if (params?.strategy) searchParams.set('strategy', params.strategy)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.date_from) searchParams.set('date_from', params.date_from)
  if (params?.date_to) searchParams.set('date_to', params.date_to)
  if (params?.page) searchParams.set('page', params.page.toString())
  if (params?.page_size) searchParams.set('page_size', params.page_size.toString())

  const res = await authFetch(`${API_URL}/api/trades?${searchParams}`)
  if (!res.ok) throw new Error('Failed to fetch trades')
  return res.json()
}

export async function fetchAnalyticsSummary(): Promise<AnalyticsSummary> {
  const res = await authFetch(`${API_URL}/api/analytics/summary`)
  if (!res.ok) throw new Error('Failed to fetch analytics')
  return res.json()
}

export async function importTosCSV(file: File): Promise<ImportResult> {
  const formData = new FormData()
  formData.append('file', file)

  const authHeaders = await getAuthHeaders()

  const res = await fetch(`${API_URL}/api/import/tos`, {
    method: 'POST',
    body: formData,
    headers: authHeaders,
  })

  if (!res.ok) {
    const error = await res.json()
    throw new Error(error.detail || 'Import failed')
  }

  return res.json()
}

export interface StrategyBreakdown {
  strategy: string
  trade_count: number
  win_count: number
  pnl_net: number
  total_fees: number
}

export interface UnderlyingBreakdown {
  underlying: string
  trade_count: number
  win_count: number
  pnl_net: number
  total_fees: number
}

export interface PnLOverTimePoint {
  date: string
  pnl: number
  cumulative_pnl: number
  underlying: string
}

export async function fetchAnalyticsByStrategy(): Promise<StrategyBreakdown[]> {
  const res = await authFetch(`${API_URL}/api/analytics/by-strategy`)
  if (!res.ok) throw new Error('Failed to fetch analytics by strategy')
  return res.json()
}

export async function fetchAnalyticsByUnderlying(): Promise<UnderlyingBreakdown[]> {
  const res = await authFetch(`${API_URL}/api/analytics/by-underlying`)
  if (!res.ok) throw new Error('Failed to fetch analytics by underlying')
  return res.json()
}

export async function fetchPnLOverTime(): Promise<PnLOverTimePoint[]> {
  const res = await authFetch(`${API_URL}/api/analytics/over-time`)
  if (!res.ok) throw new Error('Failed to fetch P&L over time')
  return res.json()
}
