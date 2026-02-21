'use client'

import React from 'react'

interface StrategyScore {
  confidence: number
  reason: string
  status: 'IDLE' | 'WATCHING' | 'WARMING_UP' | 'READY' | 'ACTIVE'
}

interface StrategyScoresProps {
  scores: Record<string, StrategyScore> | null
  loading?: boolean
}

const strategyNames: Record<string, string> = {
  A: 'EMA Cross',
  B: 'Mean Revert',
  C: 'Breakout',
  D: 'RSI/BB',
}

const statusConfig: Record<string, { color: string; bg: string; border: string }> = {
  IDLE: { color: 'text-gray-400', bg: 'bg-gray-500/10', border: 'border-gray-500/30' },
  WATCHING: { color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
  WARMING_UP: { color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30' },
  READY: { color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/30' },
  ACTIVE: { color: 'text-brand-accent-green', bg: 'bg-green-500/15', border: 'border-green-500/40' },
}

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.6) return 'bg-green-500'
  if (confidence >= 0.3) return 'bg-yellow-500'
  return 'bg-red-500'
}

export function StrategyScores({ scores, loading = false }: StrategyScoresProps) {
  if (loading || !scores) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="animate-pulse bg-gray-700/30 rounded-lg h-20" />
        ))}
      </div>
    )
  }

  const entries = Object.entries(scores)

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Strategy Scores</h4>
      {entries.map(([code, score]) => {
        const status = statusConfig[score.status] || statusConfig.IDLE
        const pct = Math.round(score.confidence * 100)

        return (
          <div
            key={code}
            className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-3 transition-all duration-300 hover:border-gray-600"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2.5">
                <span className="w-8 h-8 rounded-lg bg-purple-500/15 border border-purple-500/20 flex items-center justify-center text-sm font-bold text-purple-300">
                  {code}
                </span>
                <div>
                  <span className="text-sm font-semibold text-gray-100">
                    {strategyNames[code] || `Strategy ${code}`}
                  </span>
                </div>
              </div>
              <span
                className={`text-xs px-2 py-0.5 rounded-full font-medium border ${status.bg} ${status.color} ${status.border}`}
              >
                {score.status.replace('_', ' ')}
              </span>
            </div>

            {/* Confidence bar */}
            <div className="flex items-center gap-2 mb-1.5">
              <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ease-out ${getConfidenceColor(score.confidence)}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="text-xs font-mono text-gray-300 w-10 text-right">{pct}%</span>
            </div>

            <p className="text-xs text-gray-400 leading-relaxed">{score.reason}</p>
          </div>
        )
      })}
    </div>
  )
}
