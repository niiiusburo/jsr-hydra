'use client'

import { useEffect, useState } from 'react'
import { Card } from '@/components/ui/Card'

interface TradeStatsData {
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  profit_factor: number
  total_profit: number
  avg_profit: number
  max_drawdown: number
  sharpe_ratio: number
  best_trade: number
  worst_trade: number
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
    total_trades: 0,
    winning_trades: 0,
    losing_trades: 0,
    win_rate: 0,
    profit_factor: 0,
    total_profit: 0,
    avg_profit: 0,
    max_drawdown: 0,
    sharpe_ratio: 0,
    best_trade: 0,
    worst_trade: 0,
  })
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const params = new URLSearchParams()
        if (filters?.strategy) params.append('strategy_filter', filters.strategy)

        const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
        const headers: Record<string, string> = { 'Accept': 'application/json' }
        if (token) headers['Authorization'] = `Bearer ${token}`

        const response = await fetch(`/api/trades/stats/summary?${params}`, { headers })
        if (response.ok) {
          const data = await response.json()
          setStats(data)
        }
      } catch (error) {
        console.error('Failed to fetch trade stats:', error)
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
        <div className="text-2xl font-bold text-gray-100 mt-2">{stats.total_trades}</div>
      </Card>

      <Card className="p-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide">Win Rate</div>
        <div className="text-2xl font-bold text-green-400 mt-2">
          {(stats.win_rate * 100).toFixed(1)}%
        </div>
      </Card>

      <Card className="p-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide">Profit Factor</div>
        <div className="text-2xl font-bold text-blue-400 mt-2">
          {stats.profit_factor.toFixed(2)}
        </div>
      </Card>

      <Card className="p-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide">Net P&L</div>
        <div className={`text-2xl font-bold mt-2 ${stats.total_profit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          ${stats.total_profit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </Card>

      <Card className="p-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide">Avg Trade</div>
        <div className={`text-2xl font-bold mt-2 ${stats.avg_profit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          ${stats.avg_profit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </Card>

      <Card className="p-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide">Max Drawdown</div>
        <div className="text-2xl font-bold text-red-400 mt-2">
          ${Math.abs(stats.max_drawdown).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </Card>
    </div>
  )
}
