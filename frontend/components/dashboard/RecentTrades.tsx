'use client'

import React, { useState } from 'react'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'

interface Trade {
  id: string
  time: string
  symbol: string
  direction: string
  lots: number
  entry: number
  exit: number
  pnl: number
  status?: string
}

interface RecentTradesProps {
  trades?: Trade[]
  loading?: boolean
}

export function RecentTrades({ trades, loading = false }: RecentTradesProps) {
  const [sortBy, setSortBy] = useState<'time' | 'pnl'>('time')

  if (loading) {
    return (
      <Card title="Recent Trades">
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-10 bg-gray-700/50 rounded animate-pulse" />
          ))}
        </div>
      </Card>
    )
  }

  if (!trades || trades.length === 0) {
    return (
      <Card title="Recent Trades">
        <p className="text-gray-400 text-sm">No trades recorded yet. The engine will log trades as they execute.</p>
      </Card>
    )
  }

  const sortedTrades = [...trades].sort((a, b) => {
    if (sortBy === 'pnl') {
      return b.pnl - a.pnl
    }
    return 0
  })

  const formatTime = (timeStr: string) => {
    if (!timeStr) return '-'
    try {
      const d = new Date(timeStr)
      return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    } catch {
      return timeStr
    }
  }

  const formatPrice = (price: number, symbol: string) => {
    if (price === null || price === undefined) return '-'
    // JPY pairs use 3 digits, gold/crypto uses 2, forex uses 5
    const digits = symbol?.includes('JPY') ? 3
      : (symbol?.includes('XAU') || symbol?.includes('BTC') || symbol?.includes('ETH')) ? 2
      : 5
    return price.toFixed(digits)
  }

  return (
    <Card
      title="Recent Trades"
      footer={
        <div className="flex gap-2">
          <button
            onClick={() => setSortBy('time')}
            className={`text-xs px-2 py-1 rounded ${sortBy === 'time' ? 'bg-brand-accent-green text-black' : 'text-gray-400 hover:text-gray-300'}`}
          >
            By Time
          </button>
          <button
            onClick={() => setSortBy('pnl')}
            className={`text-xs px-2 py-1 rounded ${sortBy === 'pnl' ? 'bg-brand-accent-green text-black' : 'text-gray-400 hover:text-gray-300'}`}
          >
            By P&L
          </button>
        </div>
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-400">Time</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-400">Symbol</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-400">Dir</th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-400">Lots</th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-400">Entry</th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-400">Exit</th>
              <th className="px-3 py-2 text-right text-xs font-semibold text-gray-400">P&L</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-gray-400">Status</th>
            </tr>
          </thead>
          <tbody>
            {sortedTrades.map((trade) => (
              <tr key={trade.id} className="border-b border-gray-800 hover:bg-black/20 transition-colors">
                <td className="px-3 py-2 text-gray-300 text-xs">{formatTime(trade.time)}</td>
                <td className="px-3 py-2 font-semibold text-gray-100">{trade.symbol}</td>
                <td className="px-3 py-2">
                  <Badge variant={trade.direction === 'BUY' ? 'success' : 'danger'} dot={false}>
                    {trade.direction}
                  </Badge>
                </td>
                <td className="px-3 py-2 text-right text-gray-300">{trade.lots}</td>
                <td className="px-3 py-2 text-right text-gray-400">{formatPrice(trade.entry, trade.symbol)}</td>
                <td className="px-3 py-2 text-right text-gray-400">{formatPrice(trade.exit, trade.symbol)}</td>
                <td className={`px-3 py-2 text-right font-semibold ${trade.pnl >= 0 ? 'text-brand-accent-green' : 'text-brand-accent-red'}`}>
                  {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(2)}
                </td>
                <td className="px-3 py-2 text-center text-xs text-gray-400">{trade.status || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
