'use client'

import { useEffect, useState } from 'react'
import { Card } from '@/components/ui/Card'

interface TradeStatsData {
  totalTrades: number
  winRate: number
  profitFactor: number
  netPnL: number
  avgTrade: number
  maxDrawdown: number
}

interface TradeStatsProps {
  filters?: {
    status?: string
    strategy?: string
    symbol?: string
    dateFrom?: string
    dateTo?: string
  }
}

export function TradeStats({ filters }: TradeStatsProps) {
  const [stats, setStats] = useState<TradeStatsData>({
    totalTrades: 0,
    winRate: 0,
    profitFactor: 0,
    netPnL: 0,
    avgTrade: 0,
    maxDrawdown: 0,
  })
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const params = new URLSearchParams()
        if (filters?.status) params.append('status', filters.status)
        if (filters?.strategy) params.append('strategy', filters.strategy)
        if (filters?.symbol) params.append('symbol', filters.symbol)
        if (filters?.dateFrom) params.append('dateFrom', filters.dateFrom)
        if (filters?.dateTo) params.append('dateTo', filters.dateTo)

        const response = await fetch(`/api/trades/stats?${params}`)
        if (response.ok) {
          const data = await response.json()
          setStats(data)
        }
      } catch (error) {
        console.error('Failed to fetch trade stats:', error)
        // Use mock data
        setStats({
          totalTrades: 234,
          winRate: 0.558,
          profitFactor: 1.85,
          netPnL: 24500.75,
          avgTrade: 104.68,
          maxDrawdown: -3200.5,
        })
      } finally {
        setIsLoading(false)
      }
    }

    fetchStats()
  }, [filters])

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
        {[...Array(6)].map((_, i) => (
          <Card key={i} className="p-4 animate-pulse">
            <div className="h-8 bg-gray-700 rounded mt-2"></div>
          </Card>
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
      <Card className="p-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide">Total Trades</div>
        <div className="text-2xl font-bold text-gray-100 mt-2">{stats.totalTrades}</div>
      </Card>

      <Card className="p-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide">Win Rate</div>
        <div className="text-2xl font-bold text-green-400 mt-2">
          {(stats.winRate * 100).toFixed(1)}%
        </div>
      </Card>

      <Card className="p-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide">Profit Factor</div>
        <div className="text-2xl font-bold text-blue-400 mt-2">
          {stats.profitFactor.toFixed(2)}
        </div>
      </Card>

      <Card className="p-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide">Net P&L</div>
        <div className={`text-2xl font-bold mt-2 ${stats.netPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          ${stats.netPnL.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </Card>

      <Card className="p-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide">Avg Trade</div>
        <div className={`text-2xl font-bold mt-2 ${stats.avgTrade >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          ${stats.avgTrade.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </Card>

      <Card className="p-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide">Max Drawdown</div>
        <div className="text-2xl font-bold text-red-400 mt-2">
          ${Math.abs(stats.maxDrawdown).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </Card>
    </div>
  )
}
