'use client'

import React, { useState } from 'react'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'

interface Trade {
  id: string
  time: string
  symbol: string
  direction: 'BUY' | 'SELL'
  lots: number
  entry: number
  exit: number
  pnl: number
  strategy: string
}

interface RecentTradesProps {
  trades?: Trade[]
  loading?: boolean
}

const mockTrades: Trade[] = [
  { id: '1', time: '14:35', symbol: 'EURUSD', direction: 'BUY', lots: 1.0, entry: 1.0850, exit: 1.0875, pnl: 250, strategy: 'A' },
  { id: '2', time: '14:20', symbol: 'GBPUSD', direction: 'SELL', lots: 0.5, entry: 1.2650, exit: 1.2620, pnl: 150, strategy: 'B' },
  { id: '3', time: '14:10', symbol: 'AUDUSD', direction: 'BUY', lots: 2.0, entry: 0.6520, exit: 0.6510, pnl: -200, strategy: 'A' },
  { id: '4', time: '13:55', symbol: 'USDJPY', direction: 'SELL', lots: 1.5, entry: 148.50, exit: 148.30, pnl: 300, strategy: 'C' },
  { id: '5', time: '13:40', symbol: 'EURUSD', direction: 'BUY', lots: 0.8, entry: 1.0820, exit: 1.0845, pnl: 200, strategy: 'B' },
  { id: '6', time: '13:25', symbol: 'GBPUSD', direction: 'BUY', lots: 1.2, entry: 1.2620, exit: 1.2640, pnl: 240, strategy: 'A' },
  { id: '7', time: '13:10', symbol: 'NZDUSD', direction: 'SELL', lots: 0.5, entry: 0.6100, exit: 0.6095, pnl: -100, strategy: 'D' },
  { id: '8', time: '12:55', symbol: 'AUDUSD', direction: 'SELL', lots: 1.0, entry: 0.6550, exit: 0.6530, pnl: 200, strategy: 'C' },
  { id: '9', time: '12:40', symbol: 'USDJPY', direction: 'BUY', lots: 2.0, entry: 148.00, exit: 148.20, pnl: 400, strategy: 'B' },
  { id: '10', time: '12:25', symbol: 'EURUSD', direction: 'SELL', lots: 1.0, entry: 1.0900, exit: 1.0880, pnl: 200, strategy: 'A' },
]

export function RecentTrades({ trades = mockTrades, loading = false }: RecentTradesProps) {
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

  const sortedTrades = [...trades].sort((a, b) => {
    if (sortBy === 'pnl') {
      return b.pnl - a.pnl
    }
    return 0
  })

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
              <th className="px-3 py-2 text-center text-xs font-semibold text-gray-400">Strat</th>
            </tr>
          </thead>
          <tbody>
            {sortedTrades.map((trade) => (
              <tr key={trade.id} className="border-b border-gray-800 hover:bg-black/20 transition-colors">
                <td className="px-3 py-2 text-gray-300">{trade.time}</td>
                <td className="px-3 py-2 font-semibold text-gray-100">{trade.symbol}</td>
                <td className="px-3 py-2">
                  <Badge variant={trade.direction === 'BUY' ? 'success' : 'danger'} dot={false}>
                    {trade.direction}
                  </Badge>
                </td>
                <td className="px-3 py-2 text-right text-gray-300">{trade.lots}</td>
                <td className="px-3 py-2 text-right text-gray-400">{trade.entry.toFixed(4)}</td>
                <td className="px-3 py-2 text-right text-gray-400">{trade.exit.toFixed(4)}</td>
                <td className={`px-3 py-2 text-right font-semibold ${trade.pnl >= 0 ? 'text-brand-accent-green' : 'text-brand-accent-red'}`}>
                  {trade.pnl >= 0 ? '+' : ''}{trade.pnl}
                </td>
                <td className="px-3 py-2 text-center text-gray-400">{trade.strategy}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
