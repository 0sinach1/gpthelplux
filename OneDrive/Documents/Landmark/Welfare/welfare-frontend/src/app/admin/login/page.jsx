// src/app/admin/login/page.jsx
// Admin login page
// Sends credentials to FastAPI, stores JWT token in Zustand + localStorage

'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { adminLogin } from '@/lib/api'
import useAuthStore from '@/store/authStore'

export default function AdminLoginPage() {
    const router = useRouter()
    const { login } = useAuthStore()
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')

    const handleLogin = async () => {
        if (!username || !password) {
            setError('Please enter both username and password.')
            return
        }
        setLoading(true)
        setError('')
        try {
            const data = await adminLogin({ username, password })
            login(data.access_token)
            router.push('/admin/dashboard')
        } catch (err) {
            setError('Invalid username or password. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="min-h-[calc(100vh-64px)] flex items-center justify-center bg-slate-50 px-6">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-lg p-10 w-full max-w-md">

                <div className="w-14 h-14 bg-teal-50 rounded-xl flex items-center justify-center text-3xl mb-6">🔐</div>
                <h1 className="text-2xl font-bold text-slate-800 mb-1">Admin Login</h1>
                <p className="text-slate-400 text-sm mb-8">Welfare Unit — Administrators Only</p>

                <div className="mb-5">
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">Username</label>
                    <input
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                        placeholder="Enter username"
                        className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl text-slate-800 focus:border-teal-500 focus:outline-none transition-all"
                    />
                </div>

                <div className="mb-6">
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">Password</label>
                    <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                        placeholder="Enter password"
                        className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl text-slate-800 focus:border-teal-500 focus:outline-none transition-all"
                    />
                </div>

                {error && (
                    <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-3 mb-4 text-sm flex gap-2">
                        <span>❌</span> {error}
                    </div>
                )}

                <button
                    onClick={handleLogin}
                    disabled={loading}
                    className="w-full py-4 bg-teal-600 hover:bg-teal-700 text-white font-bold rounded-xl text-lg transition-all disabled:opacity-50"
                >
                    {loading ? 'Logging in…' : 'Login to Dashboard'}
                </button>

                <p className="text-center text-xs text-slate-400 mt-4">
                    Demo: username <strong>admin</strong> · password <strong>welfare2025</strong>
                </p>
            </div>
        </div>
    )
}
