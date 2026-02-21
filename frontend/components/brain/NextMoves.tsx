'use client'

import React from 'react'
import { Clock } from 'lucide-react'

interface NextMove {
  strategy: string
  action: string
  condition: string
  timeframe: string
  probability: number
}

interface NextMovesProps {
  moves: NextMove[] | null
  loading?: boolean
}

function getProbabilityColor(probability: number): string {
  if (probability >= 0.7) return 'text-green-400'
  if (probability >= 0.4) return 'text-yellow-400'
  return 'text-red-400'
}

function getProbabilityBg(probability: number): string {
  if (probability >= 0.7) return 'stroke-green-500'
  if (probability >= 0.4) return 'stroke-yellow-500'
  return 'stroke-red-500'
}

function CircularProgress({ value, size = 36 }: { value: number; size?: number }) {
  const strokeWidth = 3
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - value * circumference

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-gray-700"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={`${getProbabilityBg(value)} transition-all duration-700`}
        />
      </svg>
      <span className={`absolute inset-0 flex items-center justify-center text-[10px] font-mono font-bold ${getProbabilityColor(value)}`}>
        {Math.round(value * 100)}
      </span>
    </div>
  )
}

export function NextMoves({ moves, loading = false }: NextMovesProps) {
  if (loading || !moves) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="animate-pulse bg-gray-700/30 rounded-lg h-20" />
        ))}
      </div>
    )
  }

  if (moves.length === 0) {
    return (
      <div className="text-center py-6 text-gray-500 text-sm">
        No pending moves. Brain is observing...
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Next Moves</h4>
      {moves.map((move, index) => (
        <div
          key={index}
          className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-3 transition-all duration-300 hover:border-gray-600"
        >
          <div className="flex items-start gap-3">
            <CircularProgress value={move.probability} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-bold text-purple-300 bg-purple-500/15 border border-purple-500/20 px-1.5 py-0.5 rounded">
                  {move.strategy}
                </span>
                <span className="text-sm font-semibold text-gray-100 truncate">{move.action}</span>
              </div>
              <p className="text-xs text-gray-400 mb-1.5 leading-relaxed">{move.condition}</p>
              <div className="flex items-center gap-1.5">
                <Clock size={12} className="text-gray-500" />
                <span className="text-xs text-gray-500">{move.timeframe}</span>
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
