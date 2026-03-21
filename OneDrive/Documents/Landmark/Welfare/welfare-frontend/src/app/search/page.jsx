// src/app/search/page.jsx
// Updated search flow:
// Found → show package card with Request Pickup
// Not found → show notification options + any existing notifications

'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { searchPackages, searchNotifications } from '@/lib/api'
import StatusBadge from '@/components/StatusBadge'

export default function SearchPage() {
    const [query, setQuery] = useState('')
    const [packages, setPackages] = useState([])
    const [notifications, setNotifications] = useState([])
    const [loading, setLoading] = useState(false)
    const [searched, setSearched] = useState(false)
    const [error, setError] = useState('')
    const router = useRouter()

    const handleSearch = async () => {
        if (!query.trim()) return
        setLoading(true)
        setError('')
        setSearched(false)
        try {
            // Search both packages AND notifications simultaneously
            const [pkgResults, notifResults] = await Promise.all([
                searchPackages(query.trim()),
                searchNotifications(query.trim()),
            ])
            setPackages(pkgResults)
            setNotifications(notifResults)
            setSearched(true)
        } catch (err) {
            setError('Unable to connect to server. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') handleSearch()
    }

    const handleRequestPickup = (pkg) => {
        sessionStorage.setItem('selected_package', JSON.stringify(pkg))
        router.push('/pickup')
    }

    const formatDate = (dateStr) => {
        return new Date(dateStr).toLocaleDateString('en-NG', {
            day: 'numeric', month: 'short', year: 'numeric'
        })
    }

    const hasResults = packages.length > 0 || notifications.length > 0
    const nothingFound = searched && !loading && !hasResults

    return (
        <div className="min-h-[calc(100vh-64px)]">

            {/* Search Hero */}
            <div className="bg-gradient-to-r from-teal-700 to-teal-600 px-6 py-10">
                <div className="max-w-2xl mx-auto">
                    <h1 className="text-2xl font-bold text-white mb-1">
                        Find Your Package
                    </h1>
                    <p className="text-teal-200 text-sm mb-6">
                        Enter your name or registration number to locate your package
                    </p>
                    <div className="relative">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-xl">
                            🔍
                        </span>
                        <input
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Search by name or registration number…"
                            className="w-full pl-12 pr-32 py-4 rounded-xl text-lg text-slate-800 font-medium shadow-lg outline-none focus:ring-4 focus:ring-white/30"
                        />
                        <button
                            onClick={handleSearch}
                            disabled={loading}
                            className="absolute right-2 top-1/2 -translate-y-1/2 px-6 py-2.5 bg-teal-800 hover:bg-teal-900 text-white font-semibold rounded-lg transition-all disabled:opacity-50"
                        >
                            {loading ? 'Searching…' : 'Search'}
                        </button>
                    </div>
                </div>
            </div>

            {/* Results Area */}
            <div className="max-w-4xl mx-auto px-6 py-8">

                {/* Error */}
                {error && (
                    <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-6 flex gap-3 text-sm">
                        <span>❌</span> {error}
                    </div>
                )}

                {/* Loading */}
                {loading && (
                    <div className="text-center py-16 text-slate-400">
                        <div className="text-4xl mb-3 animate-pulse">📦</div>
                        <p>Searching packages…</p>
                    </div>
                )}

                {/* ── PACKAGES FOUND ── */}
                {packages.length > 0 && (
                    <div className="mb-8">
                        <p className="text-slate-500 text-sm mb-4">
                            {packages.length} package(s) found
                        </p>
                        {packages.map((pkg) => (
                            <div
                                key={pkg.id}
                                className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-4 flex flex-col sm:flex-row sm:items-center gap-4 hover:shadow-md transition-shadow"
                            >
                                <div className="flex-1">
                                    <div className="font-bold text-slate-800 text-lg">
                                        {pkg.student_name}
                                    </div>
                                    <div className="text-teal-700 font-semibold text-sm font-mono mb-2">
                                        {pkg.registration_number}
                                    </div>
                                    <div className="text-slate-500 text-sm mb-2">
                                        📦 {pkg.package_description}
                                    </div>
                                    <div className="text-slate-400 text-xs">
                                        📅 Arrived: {formatDate(pkg.date_arrived)}
                                    </div>
                                </div>
                                <div className="flex flex-col items-start sm:items-end gap-3">
                                    <StatusBadge status={pkg.status} />
                                    {pkg.status !== 'PICKED_UP' &&
                                        pkg.status !== 'PICKUP_REQUESTED' && (
                                            <button
                                                onClick={() => handleRequestPickup(pkg)}
                                                className="px-5 py-2.5 bg-teal-600 hover:bg-teal-700 text-white text-sm font-semibold rounded-lg transition-all"
                                            >
                                                Request Pickup →
                                            </button>
                                        )}
                                    {pkg.status === 'PICKUP_REQUESTED' && (
                                        <span className="text-xs text-slate-400 font-medium">
                                            Request pending…
                                        </span>
                                    )}
                                    {pkg.status === 'PICKED_UP' && (
                                        <span className="text-xs text-green-600 font-semibold">
                                            ✓ Collected
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* ── EXISTING NOTIFICATIONS ── */}
                {notifications.length > 0 && (
                    <div className="mb-8">
                        <h2 className="text-base font-bold text-slate-600 mb-3">
                            🔔 Your Notifications
                        </h2>
                        {notifications.map((notif) => (
                            <div
                                key={notif.id}
                                className="bg-amber-50 border border-amber-200 rounded-xl p-5 mb-3"
                            >
                                <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
                                    <div>
                                        <div className="font-bold text-slate-800">{notif.student_name}</div>
                                        <div className="text-teal-700 font-mono text-sm font-bold mb-1">
                                            {notif.registration_number}
                                        </div>
                                        <div className="text-slate-600 text-sm">📦 {notif.package_description}</div>
                                        {notif.sender_name && (
                                            <div className="text-slate-400 text-xs mt-1">
                                                From: {notif.sender_name}
                                            </div>
                                        )}
                                        {notif.rejection_reason && (
                                            <div className="text-red-600 text-xs mt-2 bg-red-50 px-3 py-1.5 rounded-lg">
                                                Reason: {notif.rejection_reason}
                                            </div>
                                        )}
                                    </div>
                                    <div className="flex-shrink-0">
                                        <StatusBadge status={notif.status} />
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* ── NOTHING FOUND STATE ── */}
                {nothingFound && (
                    <div className="text-center py-10">
                        <div className="text-5xl mb-4">📭</div>
                        <h2 className="text-xl font-bold text-slate-600 mb-2">
                            No packages found for "{query}"
                        </h2>
                        <p className="text-slate-400 text-sm mb-8 max-w-md mx-auto">
                            Your package may not have been registered yet.
                            You can notify the Welfare Unit that you're expecting a package
                            and they'll confirm once it arrives.
                        </p>

                        <div className="flex flex-col sm:flex-row gap-4 justify-center">
                            <button
                                onClick={() => router.push(`/notify?q=${encodeURIComponent(query)}`)}
                                className="flex items-center justify-center gap-2 px-8 py-4 bg-teal-600 hover:bg-teal-700 text-white font-semibold rounded-xl transition-all shadow-md"
                            >
                                🔔 Notify Welfare Unit
                            </button>
                            <button
                                onClick={() => { setQuery(''); setSearched(false); setPackages([]); setNotifications([]) }}
                                className="flex items-center justify-center gap-2 px-8 py-4 border-2 border-slate-200 hover:border-teal-400 text-slate-600 font-semibold rounded-xl transition-all"
                            >
                                🔍 Search Again
                            </button>
                        </div>
                    </div>
                )}

                {/* Default empty state */}
                {!searched && !loading && (
                    <div className="text-center py-16 text-slate-400">
                        <div className="text-5xl mb-4">📬</div>
                        <p className="text-lg font-semibold text-slate-500">
                            Search for your package above
                        </p>
                        <p className="text-sm mt-2">
                            Enter your name or registration number to begin
                        </p>
                    </div>
                )}
            </div>
        </div>
    )
}// src/app/search/page.jsx
// Updated search flow:
// Found → show package card with Request Pickup
// Not found → show notification options + any existing notifications

'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { searchPackages, searchNotifications } from '@/lib/api'
import StatusBadge from '@/components/StatusBadge'

export default function SearchPage() {
    const [query, setQuery] = useState('')
    const [packages, setPackages] = useState([])
    const [notifications, setNotifications] = useState([])
    const [loading, setLoading] = useState(false)
    const [searched, setSearched] = useState(false)
    const [error, setError] = useState('')
    const router = useRouter()

    const handleSearch = async () => {
        if (!query.trim()) return
        setLoading(true)
        setError('')
        setSearched(false)
        try {
            // Search both packages AND notifications simultaneously
            const [pkgResults, notifResults] = await Promise.all([
                searchPackages(query.trim()),
                searchNotifications(query.trim()),
            ])
            setPackages(pkgResults)
            setNotifications(notifResults)
            setSearched(true)
        } catch (err) {
            setError('Unable to connect to server. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') handleSearch()
    }

    const handleRequestPickup = (pkg) => {
        sessionStorage.setItem('selected_package', JSON.stringify(pkg))
        router.push('/pickup')
    }

    const formatDate = (dateStr) => {
        return new Date(dateStr).toLocaleDateString('en-NG', {
            day: 'numeric', month: 'short', year: 'numeric'
        })
    }

    const hasResults = packages.length > 0 || notifications.length > 0
    const nothingFound = searched && !loading && !hasResults

    return (
        <div className="min-h-[calc(100vh-64px)]">

            {/* Search Hero */}
            <div className="bg-gradient-to-r from-teal-700 to-teal-600 px-6 py-10">
                <div className="max-w-2xl mx-auto">
                    <h1 className="text-2xl font-bold text-white mb-1">
                        Find Your Package
                    </h1>
                    <p className="text-teal-200 text-sm mb-6">
                        Enter your name or registration number to locate your package
                    </p>
                    <div className="relative">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-xl">
                            🔍
                        </span>
                        <input
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Search by name or registration number…"
                            className="w-full pl-12 pr-32 py-4 rounded-xl text-lg text-slate-800 font-medium shadow-lg outline-none focus:ring-4 focus:ring-white/30"
                        />
                        <button
                            onClick={handleSearch}
                            disabled={loading}
                            className="absolute right-2 top-1/2 -translate-y-1/2 px-6 py-2.5 bg-teal-800 hover:bg-teal-900 text-white font-semibold rounded-lg transition-all disabled:opacity-50"
                        >
                            {loading ? 'Searching…' : 'Search'}
                        </button>
                    </div>
                </div>
            </div>

            {/* Results Area */}
            <div className="max-w-4xl mx-auto px-6 py-8">

                {/* Error */}
                {error && (
                    <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-6 flex gap-3 text-sm">
                        <span>❌</span> {error}
                    </div>
                )}

                {/* Loading */}
                {loading && (
                    <div className="text-center py-16 text-slate-400">
                        <div className="text-4xl mb-3 animate-pulse">📦</div>
                        <p>Searching packages…</p>
                    </div>
                )}

                {/* ── PACKAGES FOUND ── */}
                {packages.length > 0 && (
                    <div className="mb-8">
                        <p className="text-slate-500 text-sm mb-4">
                            {packages.length} package(s) found
                        </p>
                        {packages.map((pkg) => (
                            <div
                                key={pkg.id}
                                className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-4 flex flex-col sm:flex-row sm:items-center gap-4 hover:shadow-md transition-shadow"
                            >
                                <div className="flex-1">
                                    <div className="font-bold text-slate-800 text-lg">
                                        {pkg.student_name}
                                    </div>
                                    <div className="text-teal-700 font-semibold text-sm font-mono mb-2">
                                        {pkg.registration_number}
                                    </div>
                                    <div className="text-slate-500 text-sm mb-2">
                                        📦 {pkg.package_description}
                                    </div>
                                    <div className="text-slate-400 text-xs">
                                        📅 Arrived: {formatDate(pkg.date_arrived)}
                                    </div>
                                </div>
                                <div className="flex flex-col items-start sm:items-end gap-3">
                                    <StatusBadge status={pkg.status} />
                                    {pkg.status !== 'PICKED_UP' &&
                                        pkg.status !== 'PICKUP_REQUESTED' && (
                                            <button
                                                onClick={() => handleRequestPickup(pkg)}
                                                className="px-5 py-2.5 bg-teal-600 hover:bg-teal-700 text-white text-sm font-semibold rounded-lg transition-all"
                                            >
                                                Request Pickup →
                                            </button>
                                        )}
                                    {pkg.status === 'PICKUP_REQUESTED' && (
                                        <span className="text-xs text-slate-400 font-medium">
                                            Request pending…
                                        </span>
                                    )}
                                    {pkg.status === 'PICKED_UP' && (
                                        <span className="text-xs text-green-600 font-semibold">
                                            ✓ Collected
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* ── EXISTING NOTIFICATIONS ── */}
                {notifications.length > 0 && (
                    <div className="mb-8">
                        <h2 className="text-base font-bold text-slate-600 mb-3">
                            🔔 Your Notifications
                        </h2>
                        {notifications.map((notif) => (
                            <div
                                key={notif.id}
                                className="bg-amber-50 border border-amber-200 rounded-xl p-5 mb-3"
                            >
                                <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
                                    <div>
                                        <div className="font-bold text-slate-800">{notif.student_name}</div>
                                        <div className="text-teal-700 font-mono text-sm font-bold mb-1">
                                            {notif.registration_number}
                                        </div>
                                        <div className="text-slate-600 text-sm">📦 {notif.package_description}</div>
                                        {notif.sender_name && (
                                            <div className="text-slate-400 text-xs mt-1">
                                                From: {notif.sender_name}
                                            </div>
                                        )}
                                        {notif.rejection_reason && (
                                            <div className="text-red-600 text-xs mt-2 bg-red-50 px-3 py-1.5 rounded-lg">
                                                Reason: {notif.rejection_reason}
                                            </div>
                                        )}
                                    </div>
                                    <div className="flex-shrink-0">
                                        <StatusBadge status={notif.status} />
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* ── NOTHING FOUND STATE ── */}
                {nothingFound && (
                    <div className="text-center py-10">
                        <div className="text-5xl mb-4">📭</div>
                        <h2 className="text-xl font-bold text-slate-600 mb-2">
                            No packages found for "{query}"
                        </h2>
                        <p className="text-slate-400 text-sm mb-8 max-w-md mx-auto">
                            Your package may not have been registered yet.
                            You can notify the Welfare Unit that you're expecting a package
                            and they'll confirm once it arrives.
                        </p>

                        <div className="flex flex-col sm:flex-row gap-4 justify-center">
                            <button
                                onClick={() => router.push(`/notify?q=${encodeURIComponent(query)}`)}
                                className="flex items-center justify-center gap-2 px-8 py-4 bg-teal-600 hover:bg-teal-700 text-white font-semibold rounded-xl transition-all shadow-md"
                            >
                                🔔 Notify Welfare Unit
                            </button>
                            <button
                                onClick={() => { setQuery(''); setSearched(false); setPackages([]); setNotifications([]) }}
                                className="flex items-center justify-center gap-2 px-8 py-4 border-2 border-slate-200 hover:border-teal-400 text-slate-600 font-semibold rounded-xl transition-all"
                            >
                                🔍 Search Again
                            </button>
                        </div>
                    </div>
                )}

                {/* Default empty state */}
                {!searched && !loading && (
                    <div className="text-center py-16 text-slate-400">
                        <div className="text-5xl mb-4">📬</div>
                        <p className="text-lg font-semibold text-slate-500">
                            Search for your package above
                        </p>
                        <p className="text-sm mt-2">
                            Enter your name or registration number to begin
                        </p>
                    </div>
                )}
            </div>
        </div>
    )
}