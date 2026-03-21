// src/components/Navbar.jsx
// Fixed navigation bar shown on every page
// Shows different links depending on whether admin is logged in

'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'
import useAuthStore from '@/store/authStore'

export default function Navbar() {
  const pathname = usePathname()
  const router = useRouter()
  const { isAdmin, logout, initAuth } = useAuthStore()

  // Check localStorage for existing token when navbar first loads
  useEffect(() => {
    initAuth()
  }, [])

  const handleLogout = () => {
    logout()
    router.push('/')
  }

  // Helper to highlight the active nav link
  const isActive = (path) => pathname === path

  const linkClass = (path) =>
    `px-4 py-2 rounded-lg text-sm font-medium transition-all duration-150 ${
      isActive(path)
        ? 'bg-teal-50 text-teal-700 font-semibold'
        : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800'
    }`

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-white border-b border-slate-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">

        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 font-bold text-teal-800 text-lg">
          <div className="w-8 h-8 bg-teal-600 rounded-lg flex items-center justify-center text-white text-sm">
            📦
          </div>
          <span className="hidden sm:block">LU Welfare Portal</span>
        </Link>

        {/* Nav Links */}
        <div className="flex items-center gap-1">
          <Link href="/" className={linkClass('/')}>🏠 Home</Link>
          <Link href="/search" className={linkClass('/search')}>🔍 Search</Link>

          {/* Admin links — only shown when logged in */}
          {isAdmin && (
            <>
              <Link href="/admin/dashboard" className={linkClass('/admin/dashboard')}>
                📊 Dashboard
              </Link>
              <Link href="/admin/add" className={linkClass('/admin/add')}>
                ➕ Add Package
              </Link>
              <Link href="/admin/record" className={linkClass('/admin/record')}>
                ✅ Record Pickup
              </Link>
            </>
          )}

          {/* Login/Logout button */}
          {!isAdmin ? (
            <Link href="/admin/login" className={linkClass('/admin/login')}>
              🔐 Admin Login
            </Link>
          ) : (
            <button
              onClick={handleLogout}
              className="ml-2 px-4 py-2 rounded-lg text-sm font-medium border border-slate-200 text-slate-500 hover:border-teal-400 hover:text-teal-600 transition-all"
            >
              Logout
            </button>
          )}
        </div>

        {/* Admin badge */}
        {isAdmin && (
          <div className="hidden sm:flex items-center gap-2 bg-teal-50 text-teal-700 px-3 py-1 rounded-full text-xs font-semibold">
            👤 Admin
          </div>
        )}
      </div>
    </nav>
  )
}