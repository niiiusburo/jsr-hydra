'use client'

import React, { useEffect, useState } from 'react'
import { AccountCard } from '@/components/dashboard/AccountCard'
import { EquityChart } from '@/components/dashboard/EquityChart'
import { RegimeCard } from '@/components/dashboard/RegimeCard'
import { StrategyCards } from '@/components/dashboard/StrategyCards'
import { RecentTrades } from '@/components/dashboard/RecentTrades'
import { SystemStatus } from '@/components/dashboard/SystemStatus'
import { SkeletonGrid } from '@/components/ui/Skeleton'

interface DashboardData {
  account: any
  regime: any
  strategies: any[]
  recent_trades: any[]
  equity_curve: any[]
  system_status: any
  version: string
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const fetchDashboardData = async () => {
    try {
      setError(null)
      const response = await fetch('/api/dashboard', {
        headers: {
          'Accept': 'application/json',
        },
      })

      if (!response.ok) {
        throw new Error(`Failed to fetch dashboard data: ${response.statusText}`)
      }

      const dashboardData = await response.json()
      setData(dashboardData)
      setLastUpdate(new Date())
    } catch (err) {
      console.error('Error fetching dashboard data:', err)
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // Initial fetch
    fetchDashboardData()

    // Set up auto-refresh every 30 seconds
    const interval = setInterval(() => {
      fetchDashboardData()
    }, 30000)

    return () => clearInterval(interval)
  }, [])

  const handleRefresh = async () => {
    setLoading(true)
    await fetchDashboardData()
  }

  return (
    <div className="min-h-screen bg-brand-dark p-4 md:p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl md:text-4xl font-bold text-gray-100">Dashboard</h1>
            <p className="text-gray-400 text-sm mt-1">
              {lastUpdate ? `Last updated: ${lastUpdate.toLocaleTimeString()}` : 'Loading...'}
            </p>
          </div>
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="px-4 py-2 bg-brand-accent-green text-brand-dark rounded-lg font-semibold hover:bg-opacity-90 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        {/* Error State */}
        {error && (
          <div className="mb-6 p-4 bg-red-900/20 border border-red-700/50 rounded-lg text-red-400">
            <p className="text-sm">{error}</p>
            <button
              onClick={handleRefresh}
              className="mt-2 text-xs text-red-300 hover:text-red-200 underline"
            >
              Try again
            </button>
          </div>
        )}

        {/* Loading State */}
        {loading && !data ? (
          <SkeletonGrid />
        ) : (
          <>
            {/* Top Row: Account & Regime */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6 mb-6">
              <div className="lg:col-span-2">
                <AccountCard data={data?.account} />
              </div>
              <RegimeCard data={data?.regime} />
            </div>

            {/* Equity Chart */}
            <div className="mb-6">
              <EquityChart data={data?.equity_curve} />
            </div>

            {/* Strategies & Trades Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6 mb-6">
              <StrategyCards strategies={data?.strategies} />
              <SystemStatus data={data?.system_status} />
            </div>

            {/* Recent Trades */}
            <div>
              <RecentTrades trades={data?.recent_trades} />
            </div>

            {/* Footer Info */}
            <div className="mt-8 p-4 bg-brand-panel border border-gray-700 rounded-lg text-center text-gray-400 text-xs">
              <p>JSR Hydra v{data?.version || '1.0.0'} • Auto-refresh every 30 seconds</p>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
