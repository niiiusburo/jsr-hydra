'use client'

import { useState, useEffect } from 'react'
import { Power, LogOut } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useAppStore } from '@/store/useAppStore'

interface ConnectionStatus {
  name: string
  connected: boolean
}

interface HealthResponse {
  status: string
  services: {
    postgres: { status: string }
    redis: { status: string }
    mt5: { status: string; account: number; broker: string; balance: number }
  }
  trading: {
    dry_run: boolean
    system_status: string
    open_positions: number
  }
}

export default function Header() {
  const router = useRouter()
  const clearToken = useAppStore((state) => state.clearToken)
  const [isSystemRunning, setIsSystemRunning] = useState(false)
  const [accountEquity, setAccountEquity] = useState<number | null>(null)
  const [connectionStatuses, setConnectionStatuses] = useState<ConnectionStatus[]>([])
  const [isDryRun, setIsDryRun] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isKillSwitchLoading, setIsKillSwitchLoading] = useState(false)

  // Fetch health data from API
  const fetchHealthData = async () => {
    try {
      const response = await fetch('/api/system/health')
      if (!response.ok) {
        throw new Error(`Health check failed: ${response.statusText}`)
      }
      const data: HealthResponse = await response.json()

      // Update system running state
      setIsSystemRunning(data.trading.system_status === 'RUNNING')

      // Update account equity from MT5 balance
      setAccountEquity(data.services.mt5.balance)

      // Update dry run mode
      setIsDryRun(data.trading.dry_run)

      // Update connection statuses
      const statuses: ConnectionStatus[] = [
        { name: 'MT5', connected: data.services.mt5.status === 'connected' },
        { name: 'Redis', connected: data.services.redis.status === 'connected' },
        { name: 'DB', connected: data.services.postgres.status === 'connected' },
      ]
      setConnectionStatuses(statuses)

      setIsLoading(false)
    } catch (error) {
      console.error('Failed to fetch health data:', error)
      // Set default/error state
      setConnectionStatuses([
        { name: 'MT5', connected: false },
        { name: 'Redis', connected: false },
        { name: 'DB', connected: false },
      ])
      setIsLoading(false)
    }
  }

  // Fetch health data on component mount
  useEffect(() => {
    fetchHealthData()

    // Set up polling every 10 seconds
    const interval = setInterval(fetchHealthData, 10000)

    return () => clearInterval(interval)
  }, [])

  const handleKillSwitch = async () => {
    if (confirm('Are you sure you want to stop the trading system?')) {
      setIsKillSwitchLoading(true)
      try {
        // Get auth token from localStorage
        const token = localStorage.getItem('auth_token')
        if (!token) {
          alert('No authentication token found. Please log in.')
          setIsKillSwitchLoading(false)
          return
        }

        const response = await fetch('/api/system/kill-switch', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })

        if (!response.ok) {
          throw new Error(`Kill switch failed: ${response.statusText}`)
        }

        // Update state after successful kill switch
        setIsSystemRunning(false)
      } catch (error) {
        console.error('Kill switch error:', error)
        alert('Failed to trigger kill switch. Please try again.')
      } finally {
        setIsKillSwitchLoading(false)
      }
    }
  }

  return (
    <header className="sticky top-0 z-30 border-b border-gray-700 bg-brand-panel">
      <div className="pl-14 md:pl-6 pr-6 py-4 flex items-center justify-between">
        {/* Left Section - Status Indicator */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div
              className={`status-indicator ${
                isSystemRunning ? 'status-active' : 'status-inactive'
              }`}
            />
            <span className="text-sm font-medium">
              {isSystemRunning ? 'System Running' : 'System Stopped'}
            </span>
            {isDryRun && (
              <span className="ml-2 px-2 py-1 text-xs bg-blue-900 text-blue-200 rounded">
                DRY RUN
              </span>
            )}
            {!isDryRun && isSystemRunning && (
              <span className="ml-2 px-2 py-1 text-xs bg-green-900 text-green-200 rounded">
                LIVE
              </span>
            )}
          </div>

          {/* Connection Status */}
          <div className="hidden md:flex items-center gap-4 ml-6 pl-6 border-l border-gray-700">
            {isLoading ? (
              <span className="text-xs text-gray-400">Loading...</span>
            ) : (
              connectionStatuses.map((status) => (
                <div key={status.name} className="flex items-center gap-2">
                  <div
                    className={`status-indicator ${
                      status.connected ? 'status-active' : 'status-error'
                    }`}
                  />
                  <span className="text-xs text-gray-400">{status.name}</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Center Section - Equity Display */}
        <div className="flex flex-col items-center">
          <span className="text-xs text-gray-400">Account Balance</span>
          <span className="text-lg font-bold text-brand-accent-green">
            {isLoading || accountEquity === null
              ? '—'
              : `$${accountEquity.toLocaleString('en-US', {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}`}
          </span>
        </div>

        {/* Right Section - Kill Switch + Logout */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleKillSwitch}
            disabled={!isSystemRunning || isKillSwitchLoading}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-semibold transition-all duration-200 ${
              isSystemRunning && !isKillSwitchLoading
                ? 'btn-danger'
                : 'opacity-50 cursor-not-allowed bg-gray-700 text-gray-400'
            }`}
          >
            <Power size={18} />
            <span className="text-sm hidden sm:inline">
              {isKillSwitchLoading ? 'Stopping...' : 'Kill Switch'}
            </span>
          </button>

          <button
            onClick={() => {
              localStorage.removeItem('auth_token')
              clearToken()
              router.push('/login')
            }}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-gray-400 hover:text-gray-100 hover:bg-gray-700 transition-all duration-200"
            title="Logout"
          >
            <LogOut size={18} />
            <span className="text-sm hidden sm:inline">Logout</span>
          </button>
        </div>
      </div>
    </header>
  )
}
