'use client'

import React from 'react'
import { TrendingDown, TrendingUp, Activity, Gauge } from 'lucide-react'

interface MarketAnalysisData {
  trend: string
  momentum: string
  volatility: string
  regime: string
  regime_confidence: number
  key_levels: { [key: string]: number }
  summary: string
  symbol?: string
  symbols?: Record<
    string,
    {
      regime: string
      regime_confidence: number
      bid?: number
      spread?: number
    }
  >
}

interface MarketAnalysisProps {
  data: MarketAnalysisData | null
  loading?: boolean
}

const regimeConfig: Record<string, { label: string; color: string; bg: string; border: string }> = {
  TRENDING_UP: {
    label: 'Trending Up',
    color: 'text-green-400',
    bg: 'bg-green-500/15',
    border: 'border-green-500/30',
  },
  TRENDING_DOWN: {
    label: 'Trending Down',
    color: 'text-red-400',
    bg: 'bg-red-500/15',
    border: 'border-red-500/30',
  },
  RANGING: {
    label: 'Ranging',
    color: 'text-yellow-400',
    bg: 'bg-yellow-500/15',
    border: 'border-yellow-500/30',
  },
  VOLATILE: {
    label: 'Volatile',
    color: 'text-purple-400',
    bg: 'bg-purple-500/15',
    border: 'border-purple-500/30',
  },
}

export function MarketAnalysis({ data, loading = false }: MarketAnalysisProps) {
  if (loading || !data) {
    return (
      <div className="bg-brand-panel border border-gray-700 rounded-lg p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-gray-700/50 rounded w-1/3" />
          <div className="h-4 bg-gray-700/50 rounded w-full" />
          <div className="h-4 bg-gray-700/50 rounded w-3/4" />
          <div className="h-4 bg-gray-700/50 rounded w-2/3" />
        </div>
      </div>
    )
  }

  const regime = regimeConfig[data.regime] || regimeConfig.RANGING
  const symbolEntries = Object.entries(data.symbols || {})

  return (
    <div className="bg-brand-panel border border-gray-700 rounded-lg overflow-hidden">
      {/* Header with regime badge */}
      <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-100">Market Analysis</h3>
        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-semibold border ${regime.bg} ${regime.color} ${regime.border}`}>
          <span className="w-2 h-2 rounded-full bg-current animate-pulse" />
          {regime.label}
          <span className="text-xs opacity-75">({((data.regime_confidence ?? 0) * 100).toFixed(0)}%)</span>
        </div>
      </div>

      <div className="px-6 py-4 space-y-4">
        {/* Analysis rows */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 p-1.5 rounded bg-blue-500/10">
              {data.regime === 'TRENDING_UP' ? (
                <TrendingUp size={16} className="text-blue-400" />
              ) : (
                <TrendingDown size={16} className="text-blue-400" />
              )}
            </div>
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide font-semibold">Trend</span>
              <p className="text-sm text-gray-200 mt-0.5">{data.trend}</p>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <div className="mt-0.5 p-1.5 rounded bg-amber-500/10">
              <Activity size={16} className="text-amber-400" />
            </div>
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide font-semibold">Momentum</span>
              <p className="text-sm text-gray-200 mt-0.5">{data.momentum}</p>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <div className="mt-0.5 p-1.5 rounded bg-purple-500/10">
              <Gauge size={16} className="text-purple-400" />
            </div>
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide font-semibold">Volatility</span>
              <p className="text-sm text-gray-200 mt-0.5">{data.volatility}</p>
            </div>
          </div>
        </div>

        {/* Key Levels */}
        <div className="flex flex-wrap gap-3 pt-2 border-t border-gray-700/50">
          <span className="text-xs text-gray-500 uppercase tracking-wide font-semibold self-center">Key Levels:</span>
          {Object.entries(data.key_levels).map(([key, value]) => (
            <span
              key={key}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-gray-800 border border-gray-700 text-xs"
            >
              <span className="text-gray-400">{key.replace(/_/g, ' ').toUpperCase()}</span>
              <span className="text-gray-100 font-mono font-semibold">{typeof value === 'number' ? value.toFixed(4) : String(value)}</span>
            </span>
          ))}
        </div>

        {/* Summary */}
        <div className="p-3 rounded-lg bg-purple-500/5 border border-purple-500/10">
          <p className="text-sm text-gray-300 leading-relaxed">{data.summary}</p>
        </div>

        {/* Per-symbol brain view */}
        {symbolEntries.length > 0 && (
          <div className="pt-2 border-t border-gray-700/50">
            <div className="text-xs text-gray-500 uppercase tracking-wide font-semibold mb-2">
              Pair Brain
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
              {symbolEntries.map(([symbol, snapshot]) => {
                const symRegime = regimeConfig[snapshot.regime] || regimeConfig.RANGING
                return (
                  <div
                    key={symbol}
                    className={`rounded-md border px-3 py-2 ${symRegime.bg} ${symRegime.border}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-gray-100">{symbol}</span>
                      <span className={`text-[11px] font-medium ${symRegime.color}`}>
                        {symRegime.label}
                      </span>
                    </div>
                    <div className="mt-1 text-[11px] text-gray-300">
                      Conf {((snapshot.regime_confidence ?? 0) * 100).toFixed(0)}%
                      {snapshot.bid !== undefined && snapshot.bid !== null ? ` • ${snapshot.bid.toFixed(4)}` : ''}
                      {snapshot.spread !== undefined && snapshot.spread !== null ? ` • spr ${snapshot.spread}` : ''}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
