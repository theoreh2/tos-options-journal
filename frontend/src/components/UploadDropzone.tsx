'use client'

import { useCallback, useState } from 'react'

interface UploadDropzoneProps {
  onFileSelect: (file: File) => void
  isUploading?: boolean
}

export function UploadDropzone({ onFileSelect, isUploading = false }: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  const handleDragIn = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragOut = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)

      const files = e.dataTransfer.files
      if (files && files.length > 0) {
        const file = files[0]
        if (file.name.endsWith('.csv')) {
          onFileSelect(file)
        }
      }
    },
    [onFileSelect]
  )

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (files && files.length > 0) {
        onFileSelect(files[0])
      }
    },
    [onFileSelect]
  )

  return (
    <div
      className={`relative rounded-lg border-2 border-dashed p-12 text-center transition-colors ${
        isDragging
          ? 'border-blue-500 bg-blue-50 dark:bg-blue-950'
          : 'border-zinc-300 hover:border-zinc-400 dark:border-zinc-700'
      } ${isUploading ? 'pointer-events-none opacity-50' : ''}`}
      onDragEnter={handleDragIn}
      onDragLeave={handleDragOut}
      onDragOver={handleDrag}
      onDrop={handleDrop}
    >
      <input
        type="file"
        accept=".csv"
        onChange={handleFileInput}
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
        disabled={isUploading}
      />
      <div className="space-y-2">
        <svg
          className="mx-auto h-12 w-12 text-zinc-400"
          stroke="currentColor"
          fill="none"
          viewBox="0 0 48 48"
          aria-hidden="true"
        >
          <path
            d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <div className="text-zinc-600 dark:text-zinc-400">
          <span className="font-medium text-blue-600 dark:text-blue-400">
            Click to upload
          </span>{' '}
          or drag and drop
        </div>
        <p className="text-xs text-zinc-500">TOS Account Statement CSV only</p>
      </div>
    </div>
  )
}
