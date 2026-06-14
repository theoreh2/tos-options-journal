'use client'

interface PnLCardProps {
  title: string
  value: number
  subtitle?: string
  isCurrency?: boolean
  isPercentage?: boolean
}

export function PnLCard({ title, value, subtitle, isCurrency = true, isPercentage = false }: PnLCardProps) {
  const isPositive = value >= 0
  const colorClass = isPositive ? 'text-green-600' : 'text-red-600'

  const formatValue = () => {
    if (isPercentage) {
      return `${(value * 100).toFixed(1)}%`
    }
    if (isCurrency) {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
      }).format(value)
    }
    return value.toString()
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
      <h3 className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{title}</h3>
      <p className={`mt-2 text-3xl font-semibold ${isCurrency ? colorClass : 'text-zinc-900 dark:text-zinc-100'}`}>
        {formatValue()}
      </p>
      {subtitle && (
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{subtitle}</p>
      )}
    </div>
  )
}
