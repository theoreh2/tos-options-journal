'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from './AuthProvider'

const navItems = [
  { href: '/', label: 'Dashboard' },
  { href: '/trades', label: 'Trades' },
  { href: '/analytics', label: 'Analytics' },
  { href: '/import', label: 'Import' },
]

export function NavHeader() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, loading, signOut } = useAuth()

  const handleSignOut = async () => {
    await signOut()
    router.push('/auth/login')
    router.refresh()
  }

  return (
    <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <Link href="/" className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
          Options Journal
        </Link>
        <div className="flex items-center gap-4">
          <nav className="flex gap-1">
            {navItems.map((item) => {
              const isActive = pathname === item.href
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100'
                      : 'text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100'
                  }`}
                >
                  {item.label}
                </Link>
              )
            })}
          </nav>

          {!loading && (
            <div className="flex items-center gap-3 border-l border-zinc-200 pl-4 dark:border-zinc-700">
              {user ? (
                <>
                  <span className="text-sm text-zinc-500 hidden sm:inline">
                    {user.email}
                  </span>
                  <button
                    onClick={handleSignOut}
                    className="rounded-md px-3 py-1.5 text-sm font-medium text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                  >
                    Sign out
                  </button>
                </>
              ) : (
                <Link
                  href="/auth/login"
                  className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
                >
                  Sign in
                </Link>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
