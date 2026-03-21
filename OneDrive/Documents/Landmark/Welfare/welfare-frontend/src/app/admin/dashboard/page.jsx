// src/app/admin/dashboard/page.jsx
// Admin dashboard — shows stats cards + full packages table
// Protected: redirects to login if not authenticated

'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { getAllPackages, getDashboardStats, updatePackageStatus } from '@/lib/api'
import StatusBadge from '@/components/StatusBadge'
import useAuthStore from '@/store/authStore'
import {
    getAllPackages,
    getDashboardStats,
    updatePackageStatus,
    getAllNotifications,
    approveNotification,
    rejectNotification
} from '@/lib/api'


// Notifications panel component — lives inside dashboard file
function NotificationsPanel({ onApprove }) {
    const [notifications, setNotifications] = useState([])
    const [loading, setLoading] = useState(true)
    const [acting, setActing] = useState(null)

    useEffect(() => {
        loadNotifications()
    }, [])

    const loadNotifications = async () => {
        try {
            const data = await getAllNotifications()
            setNotifications(data)
        } catch (err) {
            console.error('Failed to load notifications')
        } finally {
            setLoading(false)
        }
    }

    const handleApprove = async (id) => {
        setActing(id)
        try {
            await approveNotification(id)
            await loadNotifications()
            onApprove()
        } catch (err) {
            alert(err.response?.data?.detail || 'Failed to approve')
        } finally {
            setActing(null)
        }
    }

    const handleReject = async (id) => {
        const reason = prompt('Rejection reason (optional):')
        setActing(id)
        try {
            await rejectNotification(id, reason)
            await loadNotifications()
        } catch (err) {
            alert('Failed to reject notification')
        } finally {
            setActing(null)
        }
    }

    if (loading) return (
        <div className="p-8 text-center text-slate-400 text-sm">Loading notifications…</div>
    )

    if (notifications.length === 0) return (
        <div className="p-8 text-center text-slate-400">
            <div className="text-3xl mb-2">✅</div>
            <p className="text-sm">No notifications yet</p>
        </div>
    )

    return (
        <div className="divide-y divide-slate-50">
            {notifications.map((notif) => (
                <div key={notif.id} className="p-4 flex flex-col sm:flex-row sm:items-center gap-4">
                    <div className="flex-1">
                        <div className="font-semibold text-slate-800">{notif.student_name}</div>
                        <div className="text-teal-700 font-mono text-sm font-bold">{notif.registration_number}</div>
                        <div className="text-slate-500 text-sm mt-0.5">{notif.package_description}</div>
                        {notif.sender_name && (
                            <div className="text-slate-400 text-xs mt-0.5">From: {notif.sender_name}</div>
                        )}
                        {notif.rejection_reason && (
                            <div className="text-red-500 text-xs mt-1">Reason: {notif.rejection_reason}</div>
                        )}
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0">
                        <StatusBadge status={notif.status} />
                        {notif.status === 'PENDING' && (
                            <>
                                <button
                                    onClick={() => handleApprove(notif.id)}
                                    disabled={acting === notif.id}
                                    className="px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white text-xs font-bold rounded-lg transition-all disabled:opacity-50"
                                >
                                    ✅ Approve
                                </button>
                                <button
                                    onClick={() => handleReject(notif.id)}
                                    disabled={acting === notif.id}
                                    className="px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 text-xs font-bold rounded-lg border border-red-200 transition-all disabled:opacity-50"
                                >
                                    ❌ Reject
                                </button>
                            </>
                        )}
                    </div>
                </div>
            ))}
        </div>
    )
}

export default function DashboardPage() {
    const router = useRouter()
    const { isAdmin, initAuth } = useAuthStore()
    const [stats, setStats] = useState(null)
    const [packages, setPackages] = useState([])
    const [filtered, setFiltered] = useState([])
    const [loading, setLoading] = useState(true)
    const [filter, setFilter] = useState('')
    const [updating, setUpdating] = useState(null)
    const [error, setError] = useState('')

    useEffect(() => {
        initAuth()
    }, [])

    useEffect(() => {
        if (isAdmin === false) {
            router.push('/admin/login')
            return
        }
        if (isAdmin) fetchData()
    }, [isAdmin])

    const fetchData = async () => {
        setLoading(true)
        try {
            const [statsData, packagesData] = await Promise.all([
                getDashboardStats(),
                getAllPackages(),
            ])
            setStats(statsData)
            setPackages(packagesData)
            setFiltered(packagesData)
        } catch (err) {
            setError('Failed to load dashboard data.')
        } finally {
            setLoading(false)
        }
    }

    const handleFilter = (q) => {
        setFilter(q)
        if (!q) {
            setFiltered(packages)
            return
        }
        setFiltered(packages.filter(p =>
            p.student_name.toLowerCase().includes(q.toLowerCase()) ||
            p.registration_number.toLowerCase().includes(q.toLowerCase())
        ))
    }

    const handleStatusUpdate = async (packageId, newStatus) => {
        setUpdating(packageId)
        try {
            await updatePackageStatus(packageId, newStatus)
            await fetchData()
        } catch (err) {
            setError('Failed to update status.')
        } finally {
            setUpdating(null)
        }
    }

    const formatDate = (dateStr) => {
        return new Date(dateStr).toLocaleDateString('en-NG', {
            day: 'numeric', month: 'short', year: 'numeric'
        })
    }

    if (loading) {
        return (
            <div className="min-h-[calc(100vh-64px)] flex items-center justify-center">
                <div className="text-center text-slate-400">
                    <div className="text-5xl mb-4 animate-pulse">📊</div>
                    <p>Loading dashboard…</p>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-[calc(100vh-64px)] px-6 py-8 max-w-7xl mx-auto">

            {/* Header */}
            <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
                <div>
                    <h1 className="text-2xl font-bold text-slate-800">Admin Dashboard</h1>
                    <p className="text-slate-400 text-sm mt-1">Package Management Overview</p>
                </div>
                <div className="flex gap-3 flex-wrap">
                    <button
                        onClick={() => router.push('/admin/display')}
                        className="px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-xl text-sm transition-all"
                    >
                        📋 Display Board
                    </button>
                    <button
                        onClick={() => router.push('/admin/add')}
                        className="px-4 py-2.5 bg-teal-600 hover:bg-teal-700 text-white font-semibold rounded-xl text-sm transition-all"
                    >
                        ➕ Add New Package
                    </button>
                </div>
            </div>

            {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-6 text-sm">
                    ❌ {error}
                </div>
            )}

            {/* Stats Cards */}
            {stats && (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
                    {[
                        { label: 'Arrived Today', value: stats.arrived_today, color: 'border-teal-500' },
                        { label: 'Awaiting Pickup', value: stats.awaiting_pickup, color: 'border-amber-500' },
                        { label: 'Pickup Requests', value: stats.pickup_requests, color: 'border-purple-500' },
                        { label: 'Emergency', value: stats.emergency_requests, color: 'border-red-500' },
                        { label: 'Picked Up', value: stats.picked_up_today, color: 'border-green-500' },
                        { label: 'Total Packages', value: stats.total_packages, color: 'border-blue-500' },
                    ].map((stat) => (
                        <div key={stat.label} className={`bg-white rounded-xl border border-slate-200 border-l-4 ${stat.color} shadow-sm p-4`}>
                            <div className="text-3xl font-bold text-slate-800">{stat.value}</div>
                            <div className="text-xs text-slate-500 font-medium mt-1">{stat.label}</div>
                        </div>
                    ))}
                </div>
            )}

            {/* ── NOTIFICATIONS PANEL ── */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden mb-8">
                <div className="flex items-center justify-between p-5 border-b border-slate-100">
                    <div className="flex items-center gap-3">
                        <h2 className="font-bold text-slate-700 text-lg">🔔 Package Notifications</h2>
                        {stats?.pending_notifications > 0 && (
                            <span className="bg-amber-100 text-amber-700 text-xs font-bold px-2.5 py-1 rounded-full">
                                {stats.pending_notifications} pending
                            </span>
                        )}
                    </div>
                </div>

                <NotificationsPanel onApprove={fetchData} />
            </div>

            {/* Packages Table */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-4 p-5 border-b border-slate-100">
                    <h2 className="font-bold text-slate-700 text-lg">All Packages</h2>
                    <input
                        type="text"
                        value={filter}
                        onChange={(e) => handleFilter(e.target.value)}
                        placeholder="🔍 Filter by name or reg number…"
                        className="px-4 py-2 border border-slate-200 rounded-lg text-sm focus:border-teal-400 focus:outline-none w-full sm:w-72"
                    />
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="bg-slate-50 border-b border-slate-100">
                                {['Student Name', 'Reg. No.', 'Package Description', 'Date Arrived', 'Status', 'Actions'].map(h => (
                                    <th key={h} className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-400">
                                        {h}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="text-center py-16 text-slate-400">
                                        <div className="text-4xl mb-3">📭</div>
                                        <p>No packages found</p>
                                    </td>
                                </tr>
                            ) : (
                                filtered.map((pkg) => (
                                    <tr key={pkg.id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                                        <td className="px-4 py-4 font-semibold text-slate-800 text-sm">{pkg.student_name}</td>
                                        <td className="px-4 py-4 font-mono text-teal-700 font-bold text-sm">{pkg.registration_number}</td>
                                        <td className="px-4 py-4 text-slate-500 text-sm max-w-[200px] truncate">{pkg.package_description}</td>
                                        <td className="px-4 py-4 text-slate-400 text-sm whitespace-nowrap">{formatDate(pkg.date_arrived)}</td>
                                        <td className="px-4 py-4"><StatusBadge status={pkg.status} /></td>
                                        <td className="px-4 py-4">
                                            <div className="flex gap-2 flex-wrap">
                                                {pkg.status !== 'PICKED_UP' && (
                                                    <button
                                                        onClick={() => router.push(`/admin/record?id=${pkg.id}&name=${encodeURIComponent(pkg.student_name)}&reg=${pkg.registration_number}&desc=${encodeURIComponent(pkg.package_description)}`)}
                                                        className="px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white text-xs font-semibold rounded-lg transition-all"
                                                    >
                                                        Record Pickup
                                                    </button>
                                                )}
                                                <select
                                                    value={pkg.status}
                                                    onChange={(e) => handleStatusUpdate(pkg.id, e.target.value)}
                                                    disabled={updating === pkg.id}
                                                    className="px-2 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 focus:border-teal-400 focus:outline-none disabled:opacity-50"
                                                >
                                                    <option value="ARRIVED">Arrived</option>
                                                    <option value="READY_FOR_PICKUP">Ready for Pickup</option>
                                                    <option value="PICKUP_REQUESTED">Pickup Requested</option>
                                                    <option value="PICKED_UP">Picked Up</option>
                                                </select>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    )
}