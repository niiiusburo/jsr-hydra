'use client'

import React from 'react'
import { Card } from '@/components/ui/Card'

interface AccountData {
  balance: number
  equity: number
  freeMargin: number
  marginLevel: number
  drawdown: number
  dailyPnL: number
}

interface AccountCardProps {
  data?: AccountData
  loading?: boolean
}

const mockData: AccountData = {
  balance: 100000,
  equity: 101500,
  freeMargin: 78200,
  marginLevel: 125.4,
  drawdown: 2.5,
  dailyPnL: 1500,
}

export function AccountCard({ data = mockData, loading = false }: AccountCardProps) {
  if (loading) {
    return (
      <Card title="Account Summary">
        <div className="space-y-4">
          <div className="h-4 bg-gray-700/50 rounded animate-pulse w-1/2" />
          <div className="h-4 bg-gray-700/50 rounded animate-pulse w-2/3" />
        </div>
      </Card>
    )
  }

  const isPnLPositive = data.dailyPnL >= 0
  const drawdownPercent = ((data.drawdown / data.balance) * 100).toFixed(2)

  return (
    <Card title="Account Summary">
      <div className="space-y-6">
        {/* Balance & Equity */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Balance</p>
            <p className="text-2xl font-bold text-gray-100">
              ${data.balance.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Equity</p>
            <p className="text-2xl font-bold text-brand-accent-green">
              ${data.equity.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </p>
          </div>
        </div>

        {/* Free Margin & Margin Level */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Free Margin</p>
            <p className="text-xl font-semibold text-gray-100">
              ${data.freeMargin.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Margin Level</p>
            <p className="text-xl font-semibold text-brand-accent-green">
              {data.marginLevel.toFixed(1)}%
            </p>
          </div>
        </div>

        {/* Drawdown Progress */}
        <div>
          <div className="flex justify-between mb-2">
            <p className="text-sm text-gray-400">Max Drawdown</p>
            <p className="text-sm font-semibold text-red-400">{drawdownPercent}%</p>
          </div>
          <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-red-500"
              style={{ width: `${Math.min(parseFloat(drawdownPercent), 100)}%` }}
            />
          </div>
        </div>

        {/* Daily P&L */}
        <div className="border-t border-gray-700 pt-4">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">Daily P&L</p>
          <div className="flex items-baseline gap-2">
            <p className={`text-3xl font-bold ${isPnLPositive ? 'text-brand-accent-green' : 'text-brand-accent-red'}`}>
              {isPnLPositive ? '+' : ''}{data.dailyPnL.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </p>
            <p className={`text-sm ${isPnLPositive ? 'text-brand-accent-green' : 'text-brand-accent-red'}`}>
              {isPnLPositive ? '↑' : '↓'}
            </p>
          </div>
        </div>
      </div>
    </Card>
  )
}
