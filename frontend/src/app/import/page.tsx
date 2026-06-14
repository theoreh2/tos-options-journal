'use client'

import { useState } from 'react'
import Link from 'next/link'
import { NavHeader } from '@/components/NavHeader'
import { UploadDropzone } from '@/components/UploadDropzone'
import { importTosCSV, type ImportResult } from '@/lib/api'

export default function ImportPage() {
  const [isUploading, setIsUploading] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleFileSelect = async (file: File) => {
    setIsUploading(true)
    setError(null)
    setResult(null)

    try {
      const importResult = await importTosCSV(file)
      setResult(importResult)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <NavHeader />

      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
        <h2 className="mb-6 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Import TOS Account Statement
        </h2>

        <div className="mb-6 rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
          <h3 className="mb-3 font-medium text-zinc-900 dark:text-zinc-100">
            How to export from thinkorswim:
          </h3>
          <ol className="list-inside list-decimal space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
            <li>Open thinkorswim desktop</li>
            <li>Go to Monitor tab &rarr; Account Statement</li>
            <li>Set your desired date range</li>
            <li>Click the hamburger icon (top right of panel)</li>
            <li>Select Export to File &rarr; save as CSV</li>
          </ol>
          <p className="mt-3 text-sm text-zinc-500">
            Note: Use Account Statement export, not Activity &amp; Positions.
          </p>
        </div>

        <UploadDropzone onFileSelect={handleFileSelect} isUploading={isUploading} />

        {isUploading && (
          <div className="mt-4 text-center text-zinc-500">Importing...</div>
        )}

        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-6 rounded-lg border border-green-200 bg-green-50 p-6 dark:border-green-800 dark:bg-green-950">
            <h3 className="mb-3 font-medium text-green-800 dark:text-green-200">
              Import Successful
            </h3>
            <div className="space-y-1 text-sm text-green-700 dark:text-green-300">
              <p>
                <span className="font-medium">File:</span> {result.filename}
              </p>
              <p>
                <span className="font-medium">Date range:</span>{' '}
                {result.date_from} to {result.date_to}
              </p>
              <p>
                <span className="font-medium">Cash events parsed:</span>{' '}
                {result.raw_events}
              </p>
              <p>
                <span className="font-medium">Trades created:</span>{' '}
                {result.trades_created}
              </p>
              <p>
                <span className="font-medium">Trades updated:</span>{' '}
                {result.trades_updated}
              </p>
            </div>

            {result.warnings.length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm font-medium text-amber-700 dark:text-amber-400">
                  Warnings ({result.warnings.length}):
                </h4>
                <ul className="mt-1 list-inside list-disc text-sm text-amber-600 dark:text-amber-500">
                  {result.warnings.slice(0, 5).map((warning, i) => (
                    <li key={i}>{warning}</li>
                  ))}
                  {result.warnings.length > 5 && (
                    <li>...and {result.warnings.length - 5} more</li>
                  )}
                </ul>
              </div>
            )}

            <Link
              href="/trades"
              className="mt-4 inline-block text-sm font-medium text-green-700 hover:text-green-800 dark:text-green-400"
            >
              View trades &rarr;
            </Link>
          </div>
        )}
      </main>
    </div>
  )
}
