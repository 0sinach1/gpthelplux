// src/store/authStore.js
// Fixed to handle server-side rendering safely
// localStorage is only available in the browser, not on the server
// So we wrap every localStorage call with a typeof window check

import { create } from 'zustand'

const useAuthStore = create((set) => ({
    isAdmin: false,
    token: null,

    login: (token) => {
        // Only access localStorage in the browser
        if (typeof window !== 'undefined') {
            localStorage.setItem('welfare_admin_token', token)
        }
        set({ isAdmin: true, token })
    },

    logout: () => {
        if (typeof window !== 'undefined') {
            localStorage.removeItem('welfare_admin_token')
        }
        set({ isAdmin: false, token: null })
    },

    initAuth: () => {
        // Only run in browser, not during server-side rendering
        if (typeof window !== 'undefined') {
            const token = localStorage.getItem('welfare_admin_token')
            if (token) {
                set({ isAdmin: true, token })
            }
        }
    },
}))

export default useAuthStore