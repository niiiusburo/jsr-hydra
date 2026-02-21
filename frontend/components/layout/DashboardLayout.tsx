'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from './Sidebar'
import Header from './Header'
import { useAppStore } from '@/store/useAppStore'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const isAuthenticated = useAppStore((state) => state.isAuthenticated)
  const token = useAppStore((state) => state.token)
  const [isChecking, setIsChecking] = useState(true)

  useEffect(() => {
    // Check both Zustand persisted state and localStorage
    const storedToken = localStorage.getItem('auth_token')
    if (!isAuthenticated && !storedToken) {
      router.replace('/login')
    } else if (storedToken && !isAuthenticated) {
      // Sync localStorage token into Zustand store
      useAppStore.getState().setToken(storedToken)
    }
    setIsChecking(false)
  }, [isAuthenticated, router])

  // Show nothing while checking auth to prevent flash of content
  if (isChecking) {
    return (
      <div className="flex h-screen items-center justify-center bg-brand-dark">
        <div className="text-gray-400">Loading...</div>
      </div>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        {/* Header */}
        <Header />

        {/* Page Content */}
        <main className="flex-1 overflow-auto bg-brand-dark">
          <div className="px-6 py-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
