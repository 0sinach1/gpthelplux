// src/app/admin/add/page.jsx
// Admin form to register a new arriving package
// Protected: redirects to login if not authenticated

'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { addPackage } from '@/lib/api'
import useAuthStore from '@/store/authStore'

export default function AddPackagePage() {
    const router = useRouter()
    const { isAdmin, initAuth } = useAuthStore()
    const [form, setForm] = useState({
        student_name: '',
        registration_number: '',
        package_description: '',
        date_arrived: new Date().toISOString().split('T')[0],
    })
    const [loading, setLoading] = useState(false)
    const [success, setSuccess] = useState(false)
    const [error, setError] = useState('')

    useEffect(() => {
        initAuth()
    }, [])

    useEffect(() => {
        if (isAdmin === false) router.push('/admin/login')
    }, [isAdmin])

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
            await addPackage(form)
            setSuccess(true)
            setForm({
                student_name: '',
                registration_number: '',
                package_description: '',
                date_arrived: new Date().toISOString().split('T')[0],
            })
        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to register package.')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="min-h-[calc(100vh-64px)] px-6 py-10">
            <div className="max-w-2xl mx-auto">

                {/* Header */}
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h1 className="text-2xl font-bold text-slate-800">Register New Package</h1>
                        <p className="text-slate-400 text-sm mt-1">Log a newly arrived package into the system</p>
                    </div>
                    <button
                        onClick={() => router.push('/admin/dashboard')}
                        className="px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-500 hover:border-teal-400 hover:text-teal-600 transition-all"
                    >
                        ← Back
                    </button>
                </div>

                {/* Success Message */}
                {success && (
                    <div className="bg-green-50 border border-green-200 text-green-700 rounded-xl p-4 mb-6 flex gap-3 items-center">
                        <span className="text-xl">✅</span>
                        <div>
                            <strong>Package registered successfully!</strong>
                            <p className="text-sm mt-0.5">The package is now searchable by the student.</p>
                        </div>
                    </div>
                )}

                <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8">

                    {/* Notice */}
                    <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800 mb-6 flex gap-3">
                        <span>ℹ️</span>
                        Package will be registered with status <strong>ARRIVED</strong>. The student can then search and request pickup.
                    </div>

                    {/* Form Fields */}
                    <div className="grid grid-cols-2 gap-5 mb-5">
                        <div>
                            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                                Student Name *
                            </label>
                            <input
                                type="text"
                                name="student_name"
                                value={form.student_name}
                                onChange={handleChange}
                                placeholder="Full name"
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
                            placeholder="e.g. Brown cardboard box, parcel from courier"
                            className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl text-slate-800 focus:border-teal-500 focus:outline-none transition-all"
                        />
                    </div>

                    <div className="mb-6">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                            Date Arrived
                        </label>
                        <input
                            type="date"
                            name="date_arrived"
                            value={form.date_arrived}
                            onChange={handleChange}
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
                        {loading ? 'Registering…' : '📦 Register Package'}
                    </button>
                </div>
            </div>
        </div>
    )
}