// src/app/notify/page.jsx
// Page where students submit a "expecting a package" notification
// Reached from the search page when no package is found

'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { createNotification } from '@/lib/api'
import { Suspense } from 'react'

function NotifyForm() {
    const router = useRouter()
    const searchParams = useSearchParams()

    const [form, setForm] = useState({
        student_name: '',
        registration_number: '',
        package_description: '',
        sender_name: '',
    })
    const [loading, setLoading] = useState(false)
    const [submitted, setSubmitted] = useState(false)
    const [error, setError] = useState('')

    // Pre-fill registration number if passed from search page
    useEffect(() => {
        const query = searchParams.get('q')
        if (query) {
            // If query looks like a reg number pre-fill that field
            if (query.includes('/')) {
                setForm(prev => ({ ...prev, registration_number: query }))
            } else {
                // Otherwise pre-fill name
                setForm(prev => ({ ...prev, student_name: query }))
            }
        }
    }, [searchParams])

    const handleChange = (e) => {
        setForm({ ...form, [e.target.name]: e.target.value })
    }

    const handleSubmit = async () => {
        if (!form.student_name || !form.registration_number || !form.package_description) {
            setError('Please fill in all required fields.')
            return
        }
        setLoading(true)
        setError('')
        try {
            await createNotification(form)
            setSubmitted(true)
        } catch (err) {
            setError(
                err.response?.data?.detail ||
                'Failed to submit notification. Please try again.'
            )
        } finally {
            setLoading(false)
        }
    }

    // Success screen
    if (submitted) {
        return (
            <div className="min-h-[calc(100vh-64px)] flex items-center justify-center px-6 py-12">
                <div className="bg-white rounded-2xl border border-slate-200 shadow-lg p-10 max-w-lg w-full text-center">
                    <div className="text-6xl mb-4">🔔</div>
                    <h2 className="text-2xl font-bold text-slate-800 mb-2">
                        Notification Submitted!
                    </h2>
                    <p className="text-slate-500 mb-6">
                        The Welfare Unit has been notified. Please check back later.
                    </p>

                    <div className="bg-slate-50 rounded-xl p-4 text-left mb-6 space-y-3">
                        {[
                            ['Your Name', form.student_name],
                            ['Reg. No.', form.registration_number],
                            ['Package', form.package_description],
                            ['Sender', form.sender_name || 'Not specified'],
                        ].map(([label, value]) => (
                            <div
                                key={label}
                                className="flex justify-between text-sm border-b border-slate-200 pb-2 last:border-0"
                            >
                                <span className="text-slate-500">{label}</span>
                                <span className="font-semibold text-slate-800">{value}</span>
                            </div>
                        ))}
                    </div>

                    <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-left text-sm text-blue-800 mb-6">
                        <strong>What happens next?</strong><br />
                        1. The Welfare Unit will check if your package has arrived<br />
                        2. If found, it will be registered under your name<br />
                        3. Search again later to see your package status<br />
                        4. You can then request pickup normally
                    </div>

                    <div className="flex gap-3">
                        <button
                            onClick={() => router.push('/search')}
                            className="flex-1 py-3 border-2 border-slate-200 hover:border-teal-400 text-slate-600 font-semibold rounded-xl transition-all"
                        >
                            🔍 Search Again
                        </button>
                        <button
                            onClick={() => router.push('/')}
                            className="flex-1 py-3 bg-teal-600 hover:bg-teal-700 text-white font-semibold rounded-xl transition-all"
                        >
                            ← Home
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
                        <h1 className="text-2xl font-bold text-slate-800">
                            Notify Welfare Unit
                        </h1>
                        <p className="text-slate-400 text-sm mt-1">
                            Let us know you're expecting a package
                        </p>
                    </div>
                    <button
                        onClick={() => router.push('/search')}
                        className="px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-500 hover:border-teal-400 hover:text-teal-600 transition-all"
                    >
                        ← Back to Search
                    </button>
                </div>

                <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8">

                    {/* Info Notice */}
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800 mb-6 flex gap-3">
                        <span>ℹ️</span>
                        <div>
                            Use this form if you searched for your package and it wasn't found.
                            The Welfare Unit will check and confirm once your package arrives.
                        </div>
                    </div>

                    {/* Form */}
                    <div className="grid grid-cols-2 gap-5 mb-5">
                        <div>
                            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                                Your Full Name *
                            </label>
                            <input
                                type="text"
                                name="student_name"
                                value={form.student_name}
                                onChange={handleChange}
                                placeholder="As it appears on your ID"
                                className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl text-slate-800 focus:border-teal-500 focus:outline-none transition-all"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                                Registration Number *
                            </label>
                            <input
                                type="text"
                                name="registration_number"
                                value={form.registration_number}
                                onChange={handleChange}
                                placeholder="e.g. CSC/23/104"
                                className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl text-slate-800 focus:border-teal-500 focus:outline-none transition-all font-mono"
                            />
                        </div>
                    </div>

                    <div className="mb-5">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                            Package Description *
                        </label>
                        <input
                            type="text"
                            name="package_description"
                            value={form.package_description}
                            onChange={handleChange}
                            placeholder="What are you expecting? e.g. Brown box from my parents"
                            className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl text-slate-800 focus:border-teal-500 focus:outline-none transition-all"
                        />
                    </div>

                    <div className="mb-6">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                            Sender Name
                            <span className="text-slate-300 font-normal ml-1">(optional)</span>
                        </label>
                        <input
                            type="text"
                            name="sender_name"
                            value={form.sender_name}
                            onChange={handleChange}
                            placeholder="Who sent the package?"
                            className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl text-slate-800 focus:border-teal-500 focus:outline-none transition-all"
                        />
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
                        {loading ? 'Submitting…' : '🔔 Submit Notification'}
                    </button>
                </div>
            </div>
        </div>
    )
}

export default function NotifyPage() {
    return (
        <Suspense fallback={
            <div className="flex items-center justify-center min-h-screen text-slate-400">
                Loading…
            </div>
        }>
            <NotifyForm />
        </Suspense>
    )
}