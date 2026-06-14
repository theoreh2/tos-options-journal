'use client'

import { useState } from 'react'
import { quickAddTrade } from '@/lib/api'

interface QuickAddTradeProps {
  onTradeAdded?: () => void
}

export function QuickAddTrade({ onTradeAdded }: QuickAddTradeProps) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return

    setLoading(true)
    setMessage(null)

    try {
      const result = await quickAddTrade(text.trim())
      if (result.success) {
        setMessage({ type: 'success', text: result.message })
        setText('')
        onTradeAdded?.()
      } else {
        setMessage({ type: 'error', text: result.message })
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to add trade' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h3 className="mb-3 text-sm font-medium text-zinc-900 dark:text-zinc-100">Quick Add Trade</h3>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="BUY +1 VERTICAL SNOW 100 29 MAY 26 260/262.5 CALL @.05 LMT"
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:placeholder-zinc-500"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !text.trim()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:focus:ring-offset-zinc-900"
        >
          {loading ? 'Adding...' : 'Add'}
        </button>
      </form>
      {message && (
        <p className={`mt-2 text-sm ${message.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>
          {message.text}
        </p>
      )}
      <p className="mt-2 text-xs text-zinc-500">
        Paste order confirmation from TOS (e.g., BUY +1 VERTICAL SNOW 100 29 MAY 26 260/262.5 CALL @.05 LMT)
      </p>
    </div>
  )
}
