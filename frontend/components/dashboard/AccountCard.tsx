'use client'

import React from 'react'
import { Card } from '@/components/ui/Card'

interface AccountData {
  balance: number
  equity: number
  freeMargin: number
  marginLevel: number
  drawdownPct: number
  profit: number
  leverage: number
  currency: string
  login?: number
  server?: string
}

interface AccountCardProps {
  data?: AccountData | null
  loading?: boolean
}

export function AccountCard({ data, loading = false }: AccountCardProps) {
  if (loading || !data) {
    return (
      <Card title="Account Summary">
        <div className="space-y-4">
          <p className="text-gray-400 text-sm">Waiting for MT5 connection...</p>
          <div className="h-4 bg-gray-700/50 rounded animate-pulse w-1/2" />
          <div className="h-4 bg-gray-700/50 rounded animate-pulse w-2/3" />
        </div>
      </Card>
    )
  }

  const isProfitPositive = data.profit >= 0

  return (
    <Card title="Account Summary">
      <div className="space-y-6">
        {/* Account Info */}
        {data.login && (
          <div className="text-xs text-gray-500">
            Account {data.login} &bull; {data.server} &bull; {data.leverage}:1 leverage
          </div>
        )}

        {/* Balance & Equity */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Balance</p>
            <p className="text-2xl font-bold text-gray-100">
              ${data.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Equity</p>
            <p className="text-2xl font-bold text-brand-accent-green">
              ${data.equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
        </div>

        {/* Free Margin & Margin Level */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Free Margin</p>
            <p className="text-xl font-semibold text-gray-100">
              ${data.freeMargin.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Margin Level</p>
            <p className="text-xl font-semibold text-brand-accent-green">
              {data.marginLevel > 0 ? `${data.marginLevel.toFixed(1)}%` : 'N/A'}
            </p>
          </div>
        </div>

        {/* Drawdown Progress */}
        <div>
          <div className="flex justify-between mb-2">
            <p className="text-sm text-gray-400">Drawdown</p>
            <p className="text-sm font-semibold text-red-400">{data.drawdownPct.toFixed(2)}%</p>
          </div>
          <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-red-500"
              style={{ width: `${Math.min(data.drawdownPct, 100)}%` }}
            />
          </div>
        </div>

        {/* Floating P&L */}
        <div className="border-t border-gray-700 pt-4">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">Floating P&L</p>
          <div className="flex items-baseline gap-2">
            <p className={`text-3xl font-bold ${isProfitPositive ? 'text-brand-accent-green' : 'text-brand-accent-red'}`}>
              {isProfitPositive ? '+$' : '-$'}{Math.abs(data.profit || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
            <p className="text-sm text-gray-400">{data.currency}</p>
          </div>
        </div>
      </div>
    </Card>
  )
}
