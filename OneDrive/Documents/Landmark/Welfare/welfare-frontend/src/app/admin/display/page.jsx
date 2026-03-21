// src/app/admin/display/page.jsx
// Airport-style display board for the welfare office
// Shows all packages that are ready for pickup
// Designed to be readable from a distance on a large screen

'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { getAllPackages } from '@/lib/api'
import useAuthStore from '@/store/authStore'

export default function DisplayBoardPage() {
    const router = useRouter()
    const { isAdmin, initAuth } = useAuthStore()
    const [packages, setPackages] = useState([])
    const [time, setTime] = useState('')
    const [date, setDate] = useState('')

    useEffect(() => {
        initAuth()
        fetchPackages()
        // Refresh packages every 30 seconds automatically
        const pkgInterval = setInterval(fetchPackages, 30000)
        // Update clock every second
        const clockInterval = setInterval(updateClock, 1000)
        updateClock()
        return () => {
            clearInterval(pkgInterval)
            clearInterval(clockInterval)
        }
    }, [])

    const fetchPackages = async () => {
        try {
            const data = await getAllPackages()
            setPackages(data.filter(p =>
                p.status === 'READY_FOR_PICKUP' || p.status === 'PICKUP_REQUESTED'
            ))
        } catch (err) {
            console.error('Failed to load packages')
        }
    }

    const updateClock = () => {
        const now = new Date()
        setTime(now.toLocaleTimeString('en-NG', { hour: '2-digit', minute: '2-digit' }))
        setDate(now.toLocaleDateString('en-NG', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }))
    }

    return (
        <div className="min-h-[calc(100vh-64px)] bg-slate-900 px-8 py-10">

            {/* Board Header */}
            <div className="text-center mb-8">
                <p className="text-slate-500 text-sm font-bold uppercase tracking-widest mb-3">
                    Landmark University — Welfare Unit
                </p>
                <div className="text-cyan-400 text-6xl font-bold tracking-tight mb-1">{time}</div>
                <div className="text-slate-500 text-base mb-6">{date}</div>
                <div className="h-px bg-slate-800 mb-6" />
                <h1 className="text-4xl font-bold text-white tracking-tight mb-2">
                    📦 READY FOR PICKUP
                </h1>
                <p className="text-slate-500">Bring your student ID and receipt (if emergency) to the Welfare Unit</p>
            </div>

            {/* Package Grid */}
            {packages.length === 0 ? (
                <div className="text-center py-20 text-slate-600">
                    <div className="text-5xl mb-4">✅</div>
                    <p className="text-xl">No packages currently awaiting pickup</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 max-w-6xl mx-auto">
                    {packages.map((pkg) => (
                        <div
                            key={pkg.id}
                            className="bg-slate-800 border border-slate-700 rounded-xl p-5 flex items-center gap-4"
                        >
                            <div className="w-2.5 h-2.5 bg-cyan-400 rounded-full flex-shrink-0 animate-pulse" />
                            <div>
                                <div className="text-white font-bold text-xl font-mono tracking-wider">
                                    {pkg.registration_number}
                                </div>
                                <div className="text-slate-400 text-sm mt-0.5">{pkg.student_name}</div>
                                {pkg.status === 'PICKUP_REQUESTED' && (
                                    <span className="inline-block mt-1 bg-red-900 text-red-300 text-xs font-bold px-2 py-0.5 rounded">
                                        EMERGENCY
                                    </span>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Back Button */}
            <div className="text-center mt-12">
                <button
                    onClick={() => router.push('/admin/dashboard')}
                    className="px-6 py-2.5 border border-slate-700 text-slate-500 hover:text-slate-300 hover:border-slate-500 rounded-xl text-sm transition-all"
                >
                    ← Back to Dashboard
                </button>
            </div>
        </div>
    )
}
