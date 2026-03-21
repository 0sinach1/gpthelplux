// src/app/layout.js
// Root layout — wraps every single page
// Navbar is placed here so it appears on all pages automatically

import { Geist } from 'next/font/google'
import './globals.css'
import Navbar from '@/components/Navbar'

const geist = Geist({ subsets: ['latin'] })

export const metadata = {
  title: 'LU Welfare Package Portal',
  description: 'Landmark University Welfare Unit Package Management System',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={`${geist.className} bg-slate-50 min-h-screen`}>
        <Navbar />
        {/* pt-16 pushes content below the fixed navbar */}
        <main className="pt-16">
          {children}
        </main>
      </body>
    </html>
  )
}
