// src/app/page.jsx
// Home page — the first thing students and admins see
// Two big action buttons + info cards about working hours and pickup days

'use client'

import Link from 'next/link'

export default function HomePage() {
  return (
    <div className="min-h-[calc(100vh-64px)] bg-gradient-to-br from-teal-50 via-slate-50 to-slate-100 flex items-center justify-center px-6 py-12">
      <div className="text-center max-w-2xl w-full">

        {/* Logo Icon */}
        <div className="w-20 h-20 bg-teal-600 rounded-2xl flex items-center justify-center text-4xl mx-auto mb-6 shadow-lg shadow-teal-200">
          📦
        </div>

        {/* Title */}
        <h1 className="text-4xl font-bold text-slate-800 tracking-tight mb-3">
          School Welfare<br />Package Portal
        </h1>
        <p className="text-slate-500 text-lg mb-10">
          Track and collect your packages from the<br />
          <strong className="text-teal-700">Landmark University Welfare Unit</strong>
        </p>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center mb-12">
          <Link
            href="/search"
            className="flex items-center justify-center gap-2 px-8 py-4 bg-teal-600 hover:bg-teal-700 text-white font-semibold rounded-xl text-lg transition-all shadow-md hover:shadow-lg hover:-translate-y-0.5"
          >
            🔍 Search for Package
          </Link>
          <Link
            href="/admin/login"
            className="flex items-center justify-center gap-2 px-8 py-4 bg-white hover:bg-slate-50 text-slate-700 font-semibold rounded-xl text-lg border-2 border-slate-200 hover:border-teal-400 transition-all"
          >
            🔐 Welfare Admin Login
          </Link>
        </div>

        {/* Info Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 max-w-2xl mx-auto">
          <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm text-left">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
              🕐 Working Hours
            </div>
            <div className="font-semibold text-slate-700 text-sm leading-relaxed">
              Monday – Saturday<br />2:00 PM – 7:00 PM
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm text-left">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
              📅 Pickup Days
            </div>
            <div className="font-semibold text-slate-700 text-sm leading-relaxed">
              Tuesday<br />Friday
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm text-left">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
              ⚡ Emergency Fee
            </div>
            <div className="font-semibold text-slate-700 text-sm leading-relaxed">
              ₦1,500<br />12hrs after request
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm text-left">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
              📍 Location
            </div>
            <div className="font-semibold text-slate-700 text-sm leading-relaxed">
              Student Affairs<br />Welfare Unit
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}