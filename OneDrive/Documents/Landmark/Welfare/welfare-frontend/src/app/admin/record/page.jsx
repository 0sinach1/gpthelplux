// src/app/admin/record/page.jsx
// Admin records physical package collection
// Can be pre-filled from dashboard via URL query params
// Protected: redirects to login if not authenticated

'use client'

import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { recordPickup, getAllPackages } from '@/lib/api'
import useAuthStore from '@/store/authStore'

function RecordPickupForm() {
    const router = useRouter()
    const searchParams = useSearchParams()
    const { isAdmin, initAuth } = useAuthStore()

    const [form, setForm] = useState({
        package_id: '',
        registration_number: '',
        collected_by: '',
        pickup_date: new Date().toISOString().split('T')[0],
        pickup_time: new Date().toTimeString().slice(0, 5),
    })
    const [displayFields, setDisplayFields] = useState({
        student_name: '',
        package_description: '',
    })
    const [packages, setPackages] = useState([])
    const [searchQuery, setSearchQuery] = useState('')
    const [showDropdown, setShowDropdown] = useState(false)
    const [loading, setLoading] = useState(false)
    const [success, setSuccess] = useState(false)
    const [error, setError] = useState('')

    useEffect(() => {
        initAuth()
    }, [])

    useEffect(() => {
        if (isAdmin === false) router.push('/admin/login')
        if (isAdmin) loadPackages()
    }, [isAdmin])

    // Pre-fill from dashboard URL params
    useEffect(() => {
        const id = searchParams.get('id')
        const name = searchParams.get('name')
        const reg = searchParams.get('reg')
        const desc = searchParams.get('desc')
        if (id && name && reg && desc) {
            setForm(prev => ({
                ...prev,
                package_id: id,
                registration_number: reg,
            }))
            setDisplayFields({ student_name: name, package_description: desc })
            setSearchQuery(`${name} — ${reg}`)
        }
    }, [searchParams])

    const loadPackages = async () => {
        try {
            const data = await getAllPackages()
            setPackages(data.filter(p => p.status !== 'PICKED_UP'))
        } catch (err) {
            console.error('Failed to load packages')
        }
    }

    const handleChange = (e) => {
        setForm({ ...form, [e.target.name]: e.target.value })
    }

    const handlePackageSearch = (q) => {
        setSearchQuery(q)
        setShowDropdown(q.length >= 2)
    }

    const handlePackageSelect = (pkg) => {
        setForm(prev => ({
            ...prev,
            package_id: pkg.id,
            registration_number: pkg.registration_number,
        }))
        setDisplayFields({
            student_name: pkg.student_name,
            package_description: pkg.package_description,
        })
        setSearchQuery(`${pkg.student_name} — ${pkg.registration_number}`)
        setShowDropdown(false)
    }

    const filteredPackages = packages.filter(p =>
        p.student_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.registration_number.toLowerCase().includes(searchQuery.toLowerCase())
    )

    const handleSubmit = async () => {
        if (!form.package_id || !form.collected_by) {
            setError('Please select a package and enter the collector name.')
            return
        }
        setLoading(true)
        setError('')
        try {
            await recordPickup(form)
            setSuccess(true)
        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to record pickup.')
        } finally {
            setLoading(false)
        }
    }

    // Success screen
    if (success) {
        return (
            <div className="min-h-[calc(100vh-64px)] flex items-center justify-center px-6 py-12">
                <div className="bg-white rounded-2xl border border-slate-200 shadow-lg p-10 max-w-lg w-full text-center">
                    <div className="text-6xl mb-4">✅</div>
                    <h2 className="text-2xl font-bold text-slate-800 mb-2">Pickup Recorded!</h2>
                    <p className="text-slate-500 mb-6">Package successfully marked as Picked Up.</p>
                    <div className="bg-slate-50 rounded-xl p-4 text-left mb-6 space-y-3">
                        {[
                            ['Student', displayFields.student_name],
                            ['Reg. No.', form.registration_number],
                            ['Package', displayFields.package_description],
                            ['Collected By', form.collected_by],
                            ['Date', form.pickup_date],
                            ['Time', form.pickup_time],
                        ].map(([label, value]) => (
                            <div key={label} className="flex justify-between text-sm border-b border-slate-200 pb-2 last:border-0">
                                <span className="text-slate-500">{label}</span>
                                <span className="font-semibold text-slate-800">{value}</span>
                            </div>
                        ))}
                    </div>
                    <div className="flex gap-3">
                        <button
                            onClick={() => { setSuccess(false); setForm({ package_id: '', registration_number: '', collected_by: '', pickup_date: new Date().toISOString().split('T')[0], pickup_time: new Date().toTimeString().slice(0, 5) }); setDisplayFields({ student_name: '', package_description: '' }); setSearchQuery('') }}
                            className="flex-1 py-3 border-2 border-slate-200 hover:border-teal-400 text-slate-600 font-semibold rounded-xl transition-all"
                        >
                            Record Another
                        </button>
                        <button
                            onClick={() => router.push('/admin/dashboard')}
                            className="flex-1 py-3 bg-teal-600 hover:bg-teal-700 text-white font-semibold rounded-xl transition-all"
                        >
                            ← Dashboard
                        </button>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-[calc(100vh-64px)] px-6 py-10">
            <div className="max-w-2xl mx-auto">

                {/* Header */}
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h1 className="text-2xl font-bold text-slate-800">Record Package Pickup</h1>
                        <p className="text-slate-400 text-sm mt-1">Mark a package as collected by the student</p>
                    </div>
                    <button
                        onClick={() => router.push('/admin/dashboard')}
                        className="px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-500 hover:border-teal-400 hover:text-teal-600 transition-all"
                    >
                        ← Back
                    </button>
                </div>

                <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8">

                    {/* Package Search */}
                    <div className="mb-5 relative">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                            Search Package
                        </label>
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => handlePackageSearch(e.target.value)}
                            placeholder="Type student name or reg number…"
                            className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl text-slate-800 focus:border-teal-500 focus:outline-none transition-all"
                        />
                        {/* Dropdown */}
                        {showDropdown && filteredPackages.length > 0 && (
                            <div className="absolute top-full left-0 right-0 z-10 bg-white border border-slate-200 rounded-xl shadow-lg mt-1 overflow-hidden">
                                {filteredPackages.map(pkg => (
                                    <div
                                        key={pkg.id}
                                        onClick={() => handlePackageSelect(pkg)}
                                        className="px-4 py-3 hover:bg-teal-50 cursor-pointer border-b border-slate-100 last:border-0 flex justify-between items-center"
                                    >
                                        <div>
                                            <div className="font-semibold text-slate-800 text-sm">{pkg.student_name}</div>
                                            <div className="text-teal-700 font-mono text-xs font-bold">{pkg.registration_number}</div>
                                        </div>
                                        <span className="text-xs text-slate-400">{pkg.status}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Auto-filled fields */}
                    <div className="grid grid-cols-2 gap-5 mb-5">
                        <div>
                            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">Student Name</label>
                            <div className="w-full px-4 py-3 bg-slate-50 rounded-xl text-slate-600 text-sm font-medium min-h-[48px]">
                                {displayFields.student_name || '—'}
                            </div>
                        </div>
                        <div>
                            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">Registration No.</label>
                            <div className="w-full px-4 py-3 bg-slate-50 rounded-xl text-teal-700 text-sm font-bold font-mono min-h-[48px]">
                                {form.registration_number || '—'}
                            </div>
                        </div>
                    </div>

                    <div className="mb-5">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">Package Description</label>
                        <div className="w-full px-4 py-3 bg-slate-50 rounded-xl text-slate-600 text-sm min-h-[48px]">
                            {displayFields.package_description || '—'}
                        </div>
                    </div>

                    {/* Collector name */}
                    <div className="mb-5">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                            Collected By *
                        </label>
                        <input
                            type="text"
                            name="collected_by"
                            value={form.collected_by}
                            onChange={handleChange}
                            placeholder="Full name of person collecting the package"
                            className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl text-slate-800 focus:border-teal-500 focus:outline-none transition-all"
                        />
                    </div>

                    {/* Date and Time */}
                    <div className="grid grid-cols-2 gap-5 mb-6">
                        <div>
                            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">Date of Pickup</label>
                            <input
                                type="date"
                                name="pickup_date"
                                value={form.pickup_date}
                                onChange={handleChange}
                                className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl text-slate-800 focus:border-teal-500 focus:outline-none transition-all"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">Time of Pickup</label>
                            <input
                                type="time"
                                name="pickup_time"
                                value={form.pickup_time}
                                onChange={handleChange}
                                className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl text-slate-800 focus:border-teal-500 focus:outline-none transition-all"
                            />
                        </div>
                    </div>

                    {error && (
                        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-3 mb-4 text-sm flex gap-2">
                            <span>❌</span> {error}
                        </div>
                    )}

                    <hr className="border-slate-100 mb-6" />

                    <button
                        onClick={handleSubmit}
                        disabled={loading}
                        className="w-full py-4 bg-teal-600 hover:bg-teal-700 text-white font-bold rounded-xl text-lg transition-all disabled:opacity-50"
                    >
                        {loading ? 'Recording…' : '✅ Record as Picked Up'}
                    </button>
                </div>
            </div>
        </div>
    )
}

export default function RecordPickupPage() {
    return (
        <Suspense fallback={<div className="flex items-center justify-center min-h-screen text-slate-400">Loading…</div>}>
            <RecordPickupForm />
        </Suspense>
    )
}