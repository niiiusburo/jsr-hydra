'use client'

import React from 'react'
import { TrendingUp, TrendingDown, Zap } from 'lucide-react'

interface XPData {
  level: number
  xp: number
  xp_to_next: number
  win_rate: number
  total_trades: number
  total_profit: number
  current_streak: number
  current_streak_type: string
}

interface ScorecardProps {
  strategyCode: string
  strategyName: string
  xpData: XPData
  allocation: number
  fitnessScore: number
  rlExpectedValue: number
  isTop?: boolean
}

const CODE_COLORS: Record<string, { badge: string; glow: string; text: string }> = {
  A: {
    badge: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
    glow: 'rgba(6, 182, 212, 0.15)',
    text: 'text-cyan-400',
  },
  B: {
    badge: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
    glow: 'rgba(168, 85, 247, 0.15)',
    text: 'text-purple-400',
  },
  C: {
    badge: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    glow: 'rgba(249, 115, 22, 0.15)',
    text: 'text-orange-400',
  },
  D: {
    badge: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
    glow: 'rgba(234, 179, 8, 0.15)',
    text: 'text-yellow-400',
  },
  E: {
    badge: 'bg-pink-500/15 text-pink-400 border-pink-500/30',
    glow: 'rgba(236, 72, 153, 0.15)',
    text: 'text-pink-400',
  },
}

function FitnessBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score)) * 100
  const color =
    score >= 0.7 ? '#00d97e' : score >= 0.4 ? '#eab308' : '#ef4444'

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[10px]">
        <span className="text-gray-500">Fitness</span>
        <span className="font-mono" style={{ color }}>
          {score.toFixed(3)}
        </span>
      </div>
      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  )
}

function XPProgressBar({ xpData }: { xpData: XPData }) {
  const pct =
    xpData.xp_to_next > 0
      ? Math.min(100, (xpData.xp / xpData.xp_to_next) * 100)
      : 100

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[10px]">
        <span className="text-gray-500">
          Lv {xpData.level} &mdash; {xpData.xp.toLocaleString()} XP
        </span>
        <span className="text-gray-600">
          {xpData.xp_to_next > 0 ? `${xpData.xp_to_next.toLocaleString()} to next` : 'MAX'}
        </span>
      </div>
      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: '#00d97e' }}
        />
      </div>
    </div>
  )
}

export function StrategyScorecard({
  strategyCode,
  strategyName,
  xpData,
  allocation,
  fitnessScore,
  rlExpectedValue,
  isTop = false,
}: ScorecardProps) {
  const colors = CODE_COLORS[strategyCode] ?? CODE_COLORS.A
  const winRatePct = xpData.win_rate * 100
  const isWinStreak = xpData.current_streak_type === 'win'
  const profitPositive = xpData.total_profit >= 0
  const evPositive = rlExpectedValue >= 0

  const cardGlow = isTop
    ? { boxShadow: `0 0 24px ${colors.glow}, 0 0 2px ${colors.glow}` }
    : {}
  const borderClass = isTop
    ? `border-[${colors.text.replace('text-', '')}]/30`
    : 'border-gray-800'

  return (
    <div
      className={`bg-[#0a0a0a] border rounded-lg p-4 space-y-3 transition-all duration-200 hover:border-gray-700 ${borderClass}`}
      style={cardGlow}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {/* Code badge */}
          <span
            className={`shrink-0 text-[11px] font-bold px-2 py-0.5 rounded border font-mono ${colors.badge}`}
          >
            {strategyCode}
          </span>
          <span className="text-sm font-semibold text-gray-200 truncate">{strategyName}</span>
          {isTop && (
            <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-[#00d97e]/10 text-[#00d97e] border border-[#00d97e]/20">
              TOP
            </span>
          )}
        </div>

        {/* Allocation badge */}
        <span className="shrink-0 text-[10px] font-mono text-gray-400 bg-gray-800/60 border border-gray-700/50 px-1.5 py-0.5 rounded">
          {allocation.toFixed(0)}%
        </span>
      </div>

      {/* XP bar */}
      <XPProgressBar xpData={xpData} />

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        {/* Win rate */}
        <div>
          <div className="text-gray-500 text-[10px]">Win Rate</div>
          <div
            className={`text-base font-bold font-mono ${
              winRatePct > 60
                ? 'text-[#00d97e]'
                : winRatePct < 40
                  ? 'text-red-400'
                  : 'text-yellow-400'
            }`}
          >
            {winRatePct.toFixed(1)}%
          </div>
        </div>

        {/* Total trades */}
        <div>
          <div className="text-gray-500 text-[10px]">Trades</div>
          <div className="text-base font-bold text-gray-300 font-mono">
            {xpData.total_trades.toLocaleString()}
          </div>
        </div>

        {/* Net P&L */}
        <div>
          <div className="text-gray-500 text-[10px]">Net P&amp;L</div>
          <div
            className={`text-sm font-bold font-mono ${
              profitPositive ? 'text-[#00d97e]' : 'text-red-400'
            }`}
          >
            {profitPositive ? '+' : ''}${xpData.total_profit.toFixed(2)}
          </div>
        </div>

        {/* Streak */}
        <div>
          <div className="text-gray-500 text-[10px]">Streak</div>
          <div className="flex items-center gap-1 mt-0.5">
            {xpData.current_streak > 0 ? (
              <span
                className={`flex items-center gap-0.5 text-xs font-bold px-1.5 py-0.5 rounded ${
                  isWinStreak
                    ? 'bg-[#00d97e]/10 text-[#00d97e] border border-[#00d97e]/20'
                    : 'bg-red-500/10 text-red-400 border border-red-500/20'
                }`}
              >
                {isWinStreak ? (
                  <TrendingUp size={10} />
                ) : (
                  <TrendingDown size={10} />
                )}
                {xpData.current_streak}W
              </span>
            ) : (
              <span className="text-xs text-gray-600">—</span>
            )}
          </div>
        </div>
      </div>

      {/* Fitness bar */}
      <FitnessBar score={fitnessScore} />

      {/* Thompson Sampling EV */}
      <div className="flex items-center justify-between text-[10px] pt-1 border-t border-gray-800/60">
        <div className="flex items-center gap-1 text-gray-500">
          <Zap size={10} />
          <span>Thompson EV</span>
        </div>
        <span
          className={`font-mono font-semibold ${
            evPositive ? 'text-[#00d97e]' : 'text-red-400'
          }`}
        >
          {evPositive ? '+' : ''}
          {rlExpectedValue.toFixed(4)}
        </span>
      </div>
    </div>
  )
}
