'use client'

import React from 'react'
import { Check, X } from 'lucide-react'

interface StrategyRegimeMatrixProps {
  blacklist: Record<string, string[]>
  onChange: (strategy: string, regime: string, enabled: boolean) => void
}

const STRATEGIES = ['A', 'B', 'C', 'D', 'E']

const REGIMES = [
  { key: 'TRENDING_UP', label: 'Trend Up', short: 'T↑' },
  { key: 'TRENDING_DOWN', label: 'Trend Down', short: 'T↓' },
  { key: 'RANGING', label: 'Ranging', short: 'RNG' },
  { key: 'VOLATILE', label: 'Volatile', short: 'VOL' },
  { key: 'QUIET', label: 'Quiet', short: 'QT' },
  { key: 'TRANSITIONING', label: 'Transitioning', short: 'TRANS' },
]

const STRATEGY_LABELS: Record<string, string> = {
  A: 'Momentum',
  B: 'Mean Rev.',
  C: 'Breakout',
  D: 'Scalp',
  E: 'Swing',
}

export function StrategyRegimeMatrix({ blacklist, onChange }: StrategyRegimeMatrixProps) {
  const isBlacklisted = (strategy: string, regime: string): boolean => {
    return (blacklist[strategy] || []).includes(regime)
  }

  const handleCellClick = (strategy: string, regime: string) => {
    const currentlyBlacklisted = isBlacklisted(strategy, regime)
    // If blacklisted → enable it (remove from blacklist). If enabled → disable (add to blacklist).
    onChange(strategy, regime, currentlyBlacklisted)
  }

  const enabledCount = STRATEGIES.reduce((acc, s) => {
    return acc + REGIMES.filter((r) => !isBlacklisted(s, r.key)).length
  }, 0)
  const totalCells = STRATEGIES.length * REGIMES.length

  return (
    <div className="rounded-xl border border-gray-700/50 bg-[#0d1117]/80 p-6 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-lg font-bold text-gray-100">Strategy / Regime Matrix</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Toggle which strategies are allowed in each market regime
          </p>
        </div>
        <span className="text-xs font-mono text-gray-400 bg-gray-900 border border-gray-700 px-2.5 py-1 rounded-lg">
          {enabledCount}/{totalCells} enabled
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse min-w-[480px]">
          <thead>
            <tr>
              <th className="w-28 py-2 pr-3 text-left">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Strategy
                </span>
              </th>
              {REGIMES.map((regime) => (
                <th
                  key={regime.key}
                  className="py-2 px-1 text-center"
                  title={regime.label}
                >
                  <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                    {regime.short}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {STRATEGIES.map((strategy, idx) => (
              <tr
                key={strategy}
                className={idx % 2 === 0 ? 'bg-gray-900/20' : ''}
              >
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded-md bg-[#00d97e]/10 border border-[#00d97e]/20 flex items-center justify-center text-xs font-bold text-[#00d97e]">
                      {strategy}
                    </span>
                    <span className="text-xs text-gray-400">
                      {STRATEGY_LABELS[strategy]}
                    </span>
                  </div>
                </td>
                {REGIMES.map((regime) => {
                  const blacklisted = isBlacklisted(strategy, regime.key)
                  return (
                    <td key={regime.key} className="py-2 px-1 text-center">
                      <button
                        onClick={() => handleCellClick(strategy, regime.key)}
                        title={`${STRATEGY_LABELS[strategy]} in ${regime.label}: ${blacklisted ? 'Disabled' : 'Enabled'}`}
                        className={`
                          w-8 h-8 rounded-md border flex items-center justify-center mx-auto
                          transition-all duration-150 cursor-pointer
                          ${blacklisted
                            ? 'border-[#e63757]/40 bg-[#e63757]/10 hover:bg-[#e63757]/20'
                            : 'border-[#00d97e]/40 bg-[#00d97e]/10 hover:bg-[#00d97e]/20'
                          }
                        `}
                      >
                        {blacklisted
                          ? <X className="w-3.5 h-3.5 text-[#e63757]" />
                          : <Check className="w-3.5 h-3.5 text-[#00d97e]" />
                        }
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-5 mt-4 pt-4 border-t border-gray-800">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded bg-[#00d97e]/20 border border-[#00d97e]/40" />
          <span className="text-xs text-gray-500">Enabled</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded bg-[#e63757]/20 border border-[#e63757]/40" />
          <span className="text-xs text-gray-500">Blacklisted</span>
        </div>
        <span className="text-xs text-gray-600 ml-auto">Click cell to toggle</span>
      </div>
    </div>
  )
}
