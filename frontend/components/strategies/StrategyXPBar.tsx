'use client'

import { useState, useEffect, useRef, useMemo } from 'react'

interface XPHistoryEntry {
  xp: number
  total_xp: number
  level: number
  won: boolean
}

export interface StrategyXPData {
  code: string
  name: string
  total_xp: number
  level: number
  level_name: string
  level_color: string
  xp_to_next_level: number
  xp_current_level: number
  xp_needed_for_level: number
  progress_pct: number
  total_trades: number
  wins: number
  win_rate: number
  best_streak: number
  current_streak: number
  current_streak_type: string
  skills_unlocked?: string[]
  xp_history?: XPHistoryEntry[]
  badges?: any[]
}

interface StrategyXPBarProps {
  data: StrategyXPData
  compact?: boolean
  rank?: number
  rlActive?: boolean
  tradesAnalyzed?: number
}

/** Tiny inline SVG sparkline for XP history */
function XPSparkline({ history, color }: { history: XPHistoryEntry[]; color: string }) {
  if (history.length < 2) return null

  const last = history.slice(-12)
  const xpValues = last.map(h => h.xp)
  const max = Math.max(...xpValues, 1)
  const min = Math.min(...xpValues, 0)
  const range = max - min || 1

  const width = 80
  const height = 20
  const points = last.map((h, i) => {
    const x = (i / (last.length - 1)) * width
    const y = height - ((h.xp - min) / range) * (height - 4) - 2
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={width} height={height} className="inline-block ml-2 align-middle">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.7"
      />
      {last.map((h, i) => {
        const x = (i / (last.length - 1)) * width
        const y = height - ((h.xp - min) / range) * (height - 4) - 2
        return (
          <circle
            key={i}
            cx={x}
            cy={y}
            r="1.5"
            fill={h.won ? '#10B981' : '#EF4444'}
            opacity="0.9"
          />
        )
      })}
    </svg>
  )
}

/** Sparkle particles that float up from the bar */
function SparkleParticles({ color, count }: { color: string; count: number }) {
  const particles = useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      id: i,
      left: `${10 + Math.random() * 80}%`,
      delay: `${Math.random() * 2}s`,
      duration: `${0.8 + Math.random() * 0.8}s`,
      size: 2 + Math.random() * 2,
    }))
  }, [count])

  return (
    <>
      {particles.map(p => (
        <div
          key={p.id}
          className="absolute rounded-full animate-sparkle-float"
          style={{
            left: p.left,
            bottom: '0',
            width: p.size,
            height: p.size,
            backgroundColor: color,
            animationDelay: p.delay,
            animationDuration: p.duration,
            animationIterationCount: 'infinite',
            boxShadow: `0 0 3px ${color}`,
          }}
        />
      ))}
    </>
  )
}

export function StrategyXPBar({ data, compact = false, rank, rlActive, tradesAnalyzed }: StrategyXPBarProps) {
  const [animatedProgress, setAnimatedProgress] = useState(0)
  const [showLevelUp, setShowLevelUp] = useState(false)
  const prevLevelRef = useRef(data.level)

  // Animate progress bar
  useEffect(() => {
    const timer = setTimeout(() => {
      setAnimatedProgress(data.progress_pct)
    }, 100)
    return () => clearTimeout(timer)
  }, [data.progress_pct])

  // Detect level-up
  useEffect(() => {
    if (data.level > prevLevelRef.current) {
      setShowLevelUp(true)
      const timer = setTimeout(() => setShowLevelUp(false), 4000)
      prevLevelRef.current = data.level
      return () => clearTimeout(timer)
    }
    prevLevelRef.current = data.level
  }, [data.level])

  // Glow intensity increases as progress approaches 100%
  const glowIntensity = Math.max(0, (data.progress_pct - 50) / 50)
  const showSparkles = data.progress_pct > 50

  const xpDisplay = data.level < 10
    ? `${data.xp_current_level} / ${data.xp_needed_for_level} XP`
    : `${data.total_xp} XP (MAX)`

  if (compact) {
    return (
      <div className="flex items-center gap-3 w-full">
        {/* Rank Badge */}
        {rank && (
          <div className="flex items-center justify-center w-5 h-5 rounded text-[10px] font-bold text-gray-400 bg-gray-700/50 shrink-0">
            #{rank}
          </div>
        )}

        {/* Level Badge */}
        <div
          className="flex items-center justify-center w-8 h-8 rounded-full text-xs font-bold text-white shrink-0"
          style={{
            backgroundColor: data.level_color,
            boxShadow: `0 0 8px ${data.level_color}40`,
          }}
        >
          {data.level}
        </div>

        {/* XP Bar */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-400 truncate">{data.level_name}</span>
            <div className="flex items-center gap-1.5">
              {rlActive && (
                <span className="animate-brain-pulse text-[10px]" title={`RL active - ${tradesAnalyzed ?? 0} trades analyzed`}>
                  🧠
                </span>
              )}
              <span className="text-xs text-gray-500">{Math.round(data.progress_pct)}%</span>
            </div>
          </div>
          <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden relative">
            <div
              className="h-full rounded-full transition-all duration-1000 ease-out"
              style={{
                width: `${animatedProgress}%`,
                background: `linear-gradient(90deg, ${data.level_color}80, ${data.level_color})`,
                boxShadow: glowIntensity > 0
                  ? `0 0 ${6 + glowIntensity * 10}px ${data.level_color}${Math.round(60 + glowIntensity * 40).toString(16)}`
                  : `0 0 6px ${data.level_color}60`,
              }}
            />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="relative">
      {/* Level-up flash animation - enhanced with scale bounce and glow burst */}
      {showLevelUp && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <div
            className="px-6 py-3 rounded-lg font-bold text-lg text-white animate-level-up-burst animate-level-up-glow"
            style={{
              backgroundColor: data.level_color,
              '--glow-color': `${data.level_color}80`,
            } as React.CSSProperties}
          >
            LEVEL UP! Level {data.level} - {data.level_name}
          </div>
        </div>
      )}

      <div className={`flex items-center gap-4 ${showLevelUp ? 'opacity-40' : ''} transition-opacity duration-300`}>
        {/* Level Badge with rank */}
        <div className="relative shrink-0">
          {rank && (
            <div className="absolute -top-1.5 -right-1.5 z-10 flex items-center justify-center w-5 h-5 rounded-full text-[9px] font-bold text-white bg-gray-800 border border-gray-600">
              #{rank}
            </div>
          )}
          <div
            className="flex flex-col items-center justify-center w-14 h-14 rounded-full text-white"
            style={{
              backgroundColor: data.level_color,
              boxShadow: glowIntensity > 0
                ? `0 0 ${12 + glowIntensity * 20}px ${data.level_color}${Math.round(50 + glowIntensity * 50).toString(16)}`
                : `0 0 12px ${data.level_color}50`,
              transition: 'box-shadow 0.5s ease',
            }}
          >
            <span className="text-lg font-bold leading-none">{data.level}</span>
            <span className="text-[9px] leading-none mt-0.5 opacity-80">LVL</span>
          </div>
        </div>

        {/* Info + Bar */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-gray-200">{data.name}</span>
              <span
                className="text-xs font-medium px-2 py-0.5 rounded-full"
                style={{
                  color: data.level_color,
                  backgroundColor: `${data.level_color}15`,
                  border: `1px solid ${data.level_color}30`,
                }}
              >
                {data.level_name}
              </span>
              {/* RL Brain indicator */}
              {rlActive && (
                <span
                  className="animate-brain-pulse text-sm cursor-default"
                  title={`RL learning active - ${tradesAnalyzed ?? 0} trades analyzed`}
                >
                  🧠
                </span>
              )}
            </div>
            <div className="flex items-center">
              <span className="text-xs text-gray-400">{xpDisplay}</span>
              {/* XP history sparkline */}
              {data.xp_history && data.xp_history.length >= 2 && (
                <XPSparkline history={data.xp_history} color={data.level_color} />
              )}
            </div>
          </div>

          {/* XP Bar with sparkles */}
          <div className="w-full h-3 bg-gray-700/50 rounded-full overflow-visible border border-gray-600/30 relative">
            <div className="absolute inset-0 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-1000 ease-out relative"
                style={{
                  width: `${animatedProgress}%`,
                  background: `linear-gradient(90deg, ${data.level_color}60, ${data.level_color}, ${data.level_color}CC)`,
                  boxShadow: glowIntensity > 0
                    ? `0 0 ${10 + glowIntensity * 16}px ${data.level_color}${Math.round(40 + glowIntensity * 60).toString(16)}, inset 0 1px 0 rgba(255,255,255,0.2)`
                    : `0 0 10px ${data.level_color}40, inset 0 1px 0 rgba(255,255,255,0.2)`,
                  transition: 'width 1s ease-out, box-shadow 0.5s ease',
                }}
              >
                {/* Shine effect */}
                <div
                  className="absolute inset-0 rounded-full"
                  style={{
                    background: 'linear-gradient(180deg, rgba(255,255,255,0.15) 0%, transparent 60%)',
                  }}
                />
                {/* Shimmer sweep when close to level up */}
                {glowIntensity > 0.5 && (
                  <div
                    className="absolute inset-0 rounded-full animate-shimmer"
                    style={{
                      background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent)',
                      width: '50%',
                    }}
                  />
                )}
              </div>
            </div>
            {/* Sparkle particles */}
            {showSparkles && (
              <div className="absolute inset-0 pointer-events-none" style={{ width: `${animatedProgress}%` }}>
                <SparkleParticles
                  color={data.level_color}
                  count={Math.min(Math.floor(glowIntensity * 6) + 2, 8)}
                />
              </div>
            )}
          </div>

          {/* Stats row */}
          <div className="flex items-center gap-4 mt-1.5">
            <span className="text-xs text-gray-500">
              {data.total_trades} trades
            </span>
            <span className="text-xs text-gray-500">
              {(data.win_rate * 100).toFixed(0)}% WR
            </span>
            {data.current_streak > 0 && (
              <span className={`text-xs ${data.current_streak_type === 'win' ? 'text-green-400' : 'text-red-400'}`}>
                {data.current_streak_type === 'win' ? '' : ''}{data.current_streak} streak
              </span>
            )}
            {data.best_streak > 0 && (
              <span className="text-xs text-yellow-500">
                Best: {data.best_streak}
              </span>
            )}
          </div>

          {/* Skills display */}
          {data.skills_unlocked && data.skills_unlocked.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {data.skills_unlocked.map(skill => (
                <span
                  key={skill}
                  className="text-[10px] font-medium px-1.5 py-0.5 rounded"
                  style={{
                    color: data.level_color,
                    backgroundColor: `${data.level_color}12`,
                    border: `1px solid ${data.level_color}25`,
                  }}
                >
                  {skill}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
