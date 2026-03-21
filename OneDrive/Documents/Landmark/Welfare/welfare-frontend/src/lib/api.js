// src/lib/api.js
// This is the central API client for the entire frontend
// Every page and component imports from here to talk to the FastAPI backend
// axios handles all HTTP requests automatically

import axios from 'axios'

// This points to your FastAPI backend
// During development it runs on localhost:8000
// When deployed it will point to your Render URL
const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

// Create an axios instance with the base URL pre-configured
// So every request automatically goes to the right server
const api = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor
// This runs BEFORE every single API request is sent
// It automatically attaches the admin JWT token to protected requests
// So we don't have to manually add the token in every component
api.interceptors.request.use((config) => {
  // Get the token from localStorage if it exists
  const token = localStorage.getItem('welfare_admin_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor
// This runs AFTER every API response comes back
// If the server returns 401 (unauthorized), it means the token expired
// So we automatically log the admin out and redirect to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('welfare_admin_token')
      window.location.href = '/admin/login'
    }
    return Promise.reject(error)
  }
)

// ── PACKAGE API FUNCTIONS ─────────────────────────────────────

// Search packages by name or registration number (student-facing)
export const searchPackages = async (query) => {
  const response = await api.get(`/api/packages/search?q=${encodeURIComponent(query)}`)
  return response.data
}

// Get all packages (admin only)
export const getAllPackages = async () => {
  const response = await api.get('/api/packages/all')
  return response.data
}

// Add a new package (admin only)
export const addPackage = async (packageData) => {
  const response = await api.post('/api/packages/add', packageData)
  return response.data
}

// Update package status (admin only)
export const updatePackageStatus = async (packageId, status) => {
  const response = await api.put(`/api/packages/${packageId}/status`, { status })
  return response.data
}

// ── PICKUP API FUNCTIONS ──────────────────────────────────────

// Submit a pickup request (student-facing)
export const requestPickup = async (requestData) => {
  const response = await api.post('/api/pickup/request', requestData)
  return response.data
}

// Record a physical package collection (admin only)
export const recordPickup = async (recordData) => {
  const response = await api.post('/api/pickup/record', recordData)
  return response.data
}

// Get all pickup requests (admin only)
export const getPickupRequests = async () => {
  const response = await api.get('/api/pickup/requests')
  return response.data
}

// Get emergency pickup requests only (admin only)
export const getEmergencyRequests = async () => {
  const response = await api.get('/api/pickup/requests/emergency')
  return response.data
}

// ── AUTH API FUNCTIONS ────────────────────────────────────────

// Admin login — returns JWT token
export const adminLogin = async (credentials) => {
  const response = await api.post('/api/auth/login', credentials)
  return response.data
}

// Get dashboard statistics (admin only)
export const getDashboardStats = async () => {
  const response = await api.get('/api/admin/dashboard')
  return response.data
}
// ── NOTIFICATION API FUNCTIONS ────────────────────────────────

// Student submits "I'm expecting a package" notification
export const createNotification = async (data) => {
  const response = await api.post('/api/notifications/create', data)
  return response.data
}

// Search notifications by name or reg number (student-facing)
export const searchNotifications = async (query) => {
  const response = await api.get(`/api/notifications/search?q=${encodeURIComponent(query)}`)
  return response.data
}

// Get all notifications (admin only)
export const getAllNotifications = async () => {
  const response = await api.get('/api/notifications')
  return response.data
}

// Get only pending notifications (admin only)
export const getPendingNotifications = async () => {
  const response = await api.get('/api/notifications/pending')
  return response.data
}

// Admin approves notification → auto-creates package
export const approveNotification = async (notificationId) => {
  const response = await api.put(`/api/notifications/${notificationId}/approve`)
  return response.data
}

// Admin rejects notification with optional reason
export const rejectNotification = async (notificationId, reason) => {
  const response = await api.put(`/api/notifications/${notificationId}/reject`, {
    rejection_reason: reason
  })
  return response.data
}
export default api
