// src/app/pickup/page.jsx
// Pickup request page
// Auto-fills from selected package stored in sessionStorage
// Student selects Normal or Emergency pickup

'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { requestPickup } from '@/lib/api'

export default function PickupPage() {
    const router = useRouter()
    const [pkg, setPkg] = useState(null)
    const [pickupType, setPickupType] = useState('normal')
    const [loading, setLoading] = useState(false)
    const [submitted, setSubmitted] = useState(false)
    const [error, setError] = useState('')

    useEffect(() => {
        // Read the package selected on the search page
        const stored = sessionStorage.getItem('selected_package')
        if (stored) {
            setPkg(JSON.parse(stored))
        } else {
            // If no package selected, send back to search
            router.push('/search')
        }
    }, [])

    const getNextPickupWindow = () => {
        const now = new Date()
        const day = now.getDay()
        const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        const pickupDays = [2, 5] // Tuesday, Friday
        let minDiff = 7
        let nextDay = 2
        for (const pd of pickupDays) {
            let diff = (pd - day + 7) % 7
            if (diff === 0) diff = 0
            if (diff < minDiff) { minDiff = diff; nextDay = pd }
        }
        const nextDate = new Date(now)
        nextDate.setDate(now.getDate() + minDiff)
        return `${days[nextDay]}, ${nextDate.toLocaleDateString('en-NG', { day: 'numeric', month: 'long' })} — 2:00 PM to 7:00 PM`
    }

    const handleSubmit = async () => {
        if (!pkg) return
        setLoading(true)
        setError('')
        try {
            await requestPickup({
                package_id: pkg.id,
                registration_number: pkg.registration_number,
                pickup_type: pickupType,
            })
            setSubmitted(true)
            sessionStorage.removeItem('selected_package')
        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to submit request. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    // Success confirmation screen
    if (submitted) {
        return (
            <div className="min-h-[calc(100vh-64px)] flex items-center justify-center px-6 py-12">
                <div className="bg-white rounded-2xl border border-slate-200 shadow-lg p-10 max-w-lg w-full text-center">
                    <div className="text-6xl mb-4">{pickupType === 'emergency' ? '⚡' : '✅'}</div>
                    <h2 className="text-2xl font-bold text-slate-800 mb-2">Pickup Request Submitted!</h2>
                    <p className="text-slate-500 mb-6">Your request has been recorded successfully.</p>

                    <div className="bg-slate-50 rounded-xl p-4 text-left mb-6 space-y-3">
                        {[
                            ['Student', pkg?.student_name],
                            ['Reg. No.', pkg?.registration_number],
                            ['Package', pkg?.package_description],
                            ['Pickup Type', pickupType === 'emergency' ? '⚡ Emergency' : '📅 Normal'],
                        ].map(([label, value]) => (
                            <div key={label} className="flex justify-between text-sm border-b border-slate-200 pb-2 last:border-0">
                                <span className="text-slate-500">{label}</span>
                                <span className="font-semibold text-slate-800">{value}</span>
                            </div>
                        ))}
                    </div>

                    {pickupType === 'emergency' ? (
                        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-left text-sm text-red-800 mb-6">
                            <strong>Next Steps:</strong><br />
                            1. Pay ₦1,500 to the Student Council Financial Secretary<br />
                            2. Collect the official receipt<br />
                            3. Return to Welfare Unit after 12 hours with your receipt
                        </div>
                    ) : (
                        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-left text-sm text-blue-800 mb-6">
                            Come to the Welfare Unit on the next <strong>Tuesday or Friday</strong> between <strong>2:00 PM – 7:00 PM</strong> to collect your package. Bring your student ID.
                        </div>
                    )}

                    <button
                        onClick={() => router.push('/')}
                        className="w-full py-3 bg-teal-600 hover:bg-teal-700 text-white font-semibold rounded-xl transition-all"
                    >
                        ← Back to Home
                    </button>
                </div>
            </div>
        )
    }

    if (!pkg) return null

    return (
        <div className="min-h-[calc(100vh-64px)] px-6 py-10">
            <div className="max-w-2xl mx-auto">

                {/* Header */}
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h1 className="text-2xl font-bold text-slate-800">Request Package Pickup</h1>
                        <p className="text-slate-500 text-sm mt-1">Choose your preferred pickup method</p>
                    </div>
                    <button onClick={() => router.push('/search')} className="px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-500 hover:border-teal-400 hover:text-teal-600 transition-all">
                        ← Back
                    </button>
                </div>

                <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8">

                    {/* Package Details */}
                    <h2 className="text-base font-semibold text-slate-700 mb-4">Package Details</h2>
                    <div className="grid grid-cols-2 gap-4 mb-6">
                        <div>
                            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">Student Name</label>
                            <div className="w-full px-4 py-3 bg-slate-50 rounded-lg text-slate-600 text-sm font-medium">{pkg.student_name}</div>
                        </div>
                        <div>
                            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">Registration No.</label>
                            <div className="w-full px-4 py-3 bg-slate-50 rounded-lg text-teal-700 text-sm font-bold font-mono">{pkg.registration_number}</div>
                        </div>
                    </div>
                    <div className="mb-6">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">Package Description</label>
                        <div className="w-full px-4 py-3 bg-slate-50 rounded-lg text-slate-600 text-sm">{pkg.package_description}</div>
                    </div>

                    <hr className="border-slate-100 mb-6" />

                    {/* Pickup Type */}
                    <h2 className="text-base font-semibold text-slate-700 mb-4">Select Pickup Type</h2>
                    <div className="grid grid-cols-2 gap-4 mb-6">
                        <button
                            onClick={() => setPickupType('normal')}
                            className={`p-5 rounded-xl border-2 text-center transition-all ${pickupType === 'normal' ? 'border-teal-500 bg-teal-50' : 'border-slate-200 hover:border-teal-300'}`}
                        >
                            <div className="text-3xl mb-2">📅</div>
                            <div className={`font-bold text-sm mb-1 ${pickupType === 'normal' ? 'text-teal-700' : 'text-slate-700'}`}>Normal Pickup</div>
                            <div className="text-xs text-slate-500">Tuesday & Friday only</div>
                        </button>
                        <button
                            onClick={() => setPickupType('emergency')}
                            className={`p-5 rounded-xl border-2 text-center transition-all ${pickupType === 'emergency' ? 'border-red-400 bg-red-50' : 'border-slate-200 hover:border-red-300'}`}
                        >
                            <div className="text-3xl mb-2">⚡</div>
                            <div className={`font-bold text-sm mb-1 ${pickupType === 'emergency' ? 'text-red-700' : 'text-slate-700'}`}>Emergency Pickup</div>
                            <div className="text-xs text-slate-500">12 hours after request</div>
                        </button>
                    </div>

                    {/* Info notice */}
                    {pickupType === 'normal' && (
                        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800 mb-6 flex gap-3">
                            <span>📆</span>
                            <div><strong>Next Pickup Window:</strong> {getNextPickupWindow()}<br />
                                <span className="text-xs text-blue-600">Office hours: Mon – Sat, 2:00 PM – 7:00 PM</span></div>
                        </div>
                    )}
                    {pickupType === 'emergency' && (
                        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-800 mb-6 flex gap-3">
                            <span>⚠️</span>
                            <div>
                                <strong>Emergency Pickup Fee: ₦1,500</strong><br />
                                1. Pay ₦1,500 to the Student Council Financial Secretary<br />
                                2. Obtain an official receipt<br />
                                3. Bring the receipt to the Welfare Unit to collect your package<br />
                                4. Package available <strong>12 hours</strong> after this request
                            </div>
                        </div>
                    )}

                    {error && (
                        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-4 text-sm">❌ {error}</div>
                    )}

                    <button
                        onClick={handleSubmit}
                        disabled={loading}
                        className="w-full py-4 bg-teal-600 hover:bg-teal-700 text-white font-bold rounded-xl text-lg transition-all disabled:opacity-50"
                    >
                        {loading ? 'Submitting…' : 'Submit Pickup Request'}
                    </button>
                </div>
            </div>
        </div>
    )
}