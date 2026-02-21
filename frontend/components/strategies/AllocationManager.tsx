'use client'

import { useState, useEffect, useCallback } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts'
import { Card } from '@/components/ui/Card'

interface StrategyInfo {
  code: string
  name: string
  allocation_pct: number
}

interface FitnessBreakdown {
  xp_level: { value: number; score: number; weight: number }
  win_rate: { value: number; score: number; weight: number }
  profit_factor: { value: number; score: number; weight: number }
  rl_expected: { value: number; score: number; weight: number }
  streak: { value: string; score: number; weight: number }
}

interface FitnessScore {
  score: number
  breakdown: FitnessBreakdown
  total_trades: number
  total_profit: number
}

interface RebalanceEvent {
  timestamp: string
  rebalance_number: number
  allocations: Record<string, number>
  fitness_scores: Record<string, number>
  changes: Record<string, { from: number; to: number; delta: number }>
}

interface AutoAllocationStatus {
  enabled: boolean
  trades_since_rebalance: number
  rebalance_interval: number
  trades_until_next: number
  total_rebalances: number
  last_rebalance_time: string | null
  last_fitness_scores: Record<string, FitnessScore>
  last_allocations: Record<string, number>
  rebalance_history: RebalanceEvent[]
  config: {
    rebalance_interval: number
    max_change_per_rebalance: number
    min_allocation_pct: number
    max_allocation_pct: number
    weights: Record<string, number>
  }
}

interface AllocationManagerProps {
  strategies: StrategyInfo[]
  onSave?: (allocations: Record<string, number>) => void
}

const STRATEGY_COLORS: Record<string, string> = {
  STRATEGY_A: '#00d97e',
  STRATEGY_B: '#3b82f6',
  STRATEGY_C: '#f59e0b',
  STRATEGY_D: '#ef4444',
  STRATEGY_E: '#14b8a6',
  A: '#00d97e',
  B: '#3b82f6',
  C: '#f59e0b',
  D: '#ef4444',
  E: '#14b8a6',
}

const DEFAULT_COLOR = '#6b7280'

export function AllocationManager({ strategies, onSave }: AllocationManagerProps) {
  const [allocations, setAllocations] = useState<Record<string, number>>({})
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [autoStatus, setAutoStatus] = useState<AutoAllocationStatus | null>(null)
  const [isAutoMode, setIsAutoMode] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  // Initialize allocations from strategies prop
  useEffect(() => {
    if (strategies && strategies.length > 0) {
      const initial: Record<string, number> = {}
      strategies.forEach(s => {
        initial[s.code] = s.allocation_pct ?? 0
      })
      setAllocations(initial)
    }
  }, [strategies])

  // Fetch auto-allocation status
  const fetchAutoStatus = useCallback(async () => {
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
      const headers: Record<string, string> = { 'Accept': 'application/json' }
      if (token) headers['Authorization'] = `Bearer ${token}`

      const res = await fetch('/api/brain/auto-allocation-status', { headers })
      if (res.ok) {
        const data = await res.json()
        setAutoStatus(data)
        setIsAutoMode(data.enabled)
      }
    } catch {
      // Silently fail - auto-allocation may not be available
    }
  }, [])

  useEffect(() => {
    fetchAutoStatus()
    const interval = setInterval(fetchAutoStatus, 15000)
    return () => clearInterval(interval)
  }, [fetchAutoStatus])

  const total = Object.values(allocations).reduce((sum, val) => sum + val, 0)
  const isValid = total <= 100

  const handleAllocationChange = (code: string, value: number) => {
    const clampedValue = Math.max(0, Math.min(100, value))

    setAllocations(prev => {
      const next = {
        ...prev,
        [code]: clampedValue,
      }

      const total = Object.values(next).reduce((sum, val) => sum + val, 0)
      if (total <= 100) {
        return next
      }

      // Keep edited strategy at requested value; reduce others to maintain 100%.
      let overflow = total - 100
      const otherCodes = Object.keys(next)
        .filter(k => k !== code)
        .sort((a, b) => (next[b] ?? 0) - (next[a] ?? 0))

      for (const otherCode of otherCodes) {
        if (overflow <= 0) break
        const current = next[otherCode] ?? 0
        if (current <= 0) continue

        const reduction = Math.min(current, overflow)
        next[otherCode] = Number((current - reduction).toFixed(1))
        overflow = Number((overflow - reduction).toFixed(6))
      }

      if (overflow > 0) {
        // Safety fallback in edge cases.
        next[code] = Number(Math.max(0, (next[code] ?? 0) - overflow).toFixed(1))
      }

      return next
    })
  }

  const handleToggleAuto = async () => {
    const newEnabled = !isAutoMode
    setIsAutoMode(newEnabled)
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (token) headers['Authorization'] = `Bearer ${token}`

      await fetch('/api/brain/auto-allocation-status', {
        method: 'PATCH',
        headers,
        body: JSON.stringify({ enabled: newEnabled }),
      })
      fetchAutoStatus()
    } catch {
      setIsAutoMode(!newEnabled) // Revert on error
    }
  }

  const handleApplyBrainRecommendations = () => {
    if (autoStatus?.last_allocations) {
      const newAllocs: Record<string, number> = {}
      strategies.forEach(s => {
        newAllocs[s.code] = autoStatus.last_allocations[s.code] ?? allocations[s.code] ?? 0
      })
      setAllocations(newAllocs)
    }
  }

  const handleSave = async () => {
    if (!isValid) return

    setIsSaving(true)
    setSaveError(null)
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      }
      if (token) headers['Authorization'] = `Bearer ${token}`

      const roundedAllocations = Object.fromEntries(
        Object.entries(allocations).map(([code, value]) => [
          code,
          Number((value ?? 0).toFixed(1)),
        ])
      )

      const response = await fetch('/api/strategies/allocations', {
        method: 'PATCH',
        headers,
        body: JSON.stringify({ allocations: roundedAllocations }),
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        const detail = payload?.detail
        const detailMessage =
          typeof detail === 'string'
            ? detail
            : typeof detail?.message === 'string'
              ? detail.message
              : null
        throw new Error(detailMessage || 'Failed to update allocations')
      }

      onSave?.(roundedAllocations)
    } catch (error) {
      console.error('Failed to save allocations:', error)
      setSaveError(error instanceof Error ? error.message : 'Failed to save allocations')
    } finally {
      setIsSaving(false)
    }
  }

  const chartData = strategies
    .filter(s => (allocations[s.code] ?? 0) > 0)
    .map(s => ({
      name: s.name,
      value: allocations[s.code] ?? 0,
      color: STRATEGY_COLORS[s.code] || DEFAULT_COLOR,
    }))

  if (!strategies || strategies.length === 0) {
    return null
  }

  const hasBrainRecommendations = autoStatus?.last_allocations && Object.keys(autoStatus.last_allocations).length > 0

  return (
    <Card title="Allocation Manager" className="space-y-6">
      {/* Auto/Manual Toggle */}
      <div className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg border border-gray-700">
        <div className="flex items-center gap-3">
          <div className={`w-2 h-2 rounded-full ${isAutoMode ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`} />
          <span className="text-sm font-medium text-gray-200">
            {isAutoMode ? 'Auto (Brain-Powered)' : 'Manual Mode'}
          </span>
          {isAutoMode && autoStatus && (
            <span className="text-xs text-gray-500">
              {autoStatus.trades_until_next} trades until next rebalance
            </span>
          )}
        </div>
        <button
          onClick={handleToggleAuto}
          className={`
            relative inline-flex h-6 w-11 items-center rounded-full transition-colors
            ${isAutoMode ? 'bg-green-500' : 'bg-gray-600'}
          `}
        >
          <span
            className={`
              inline-block h-4 w-4 transform rounded-full bg-white transition-transform
              ${isAutoMode ? 'translate-x-6' : 'translate-x-1'}
            `}
          />
        </button>
      </div>

      {/* Brain Recommendations Banner */}
      {hasBrainRecommendations && !isAutoMode && (
        <div className="p-3 bg-purple-900/20 border border-purple-700/30 rounded-lg">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              <span className="text-sm text-purple-300">Brain has recommendations</span>
            </div>
            <button
              onClick={handleApplyBrainRecommendations}
              className="text-xs px-3 py-1 bg-purple-600 hover:bg-purple-500 text-white rounded-md transition-colors"
            >
              Apply Brain Recommendations
            </button>
          </div>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-8">
        {/* Sliders with Fitness Overlay */}
        <div className="space-y-6">
          {strategies.map((strategy) => {
            const color = STRATEGY_COLORS[strategy.code] || DEFAULT_COLOR
            const fitness = autoStatus?.last_fitness_scores?.[strategy.code]
            const brainAlloc = autoStatus?.last_allocations?.[strategy.code]

            return (
              <div key={strategy.code} className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-gray-300">
                    {strategy.name}
                  </label>
                  <div className="flex items-center gap-2">
                    {brainAlloc !== undefined && brainAlloc !== allocations[strategy.code] && (
                      <span className="text-xs text-purple-400" title="Brain recommendation">
                        {brainAlloc}%
                      </span>
                    )}
                    <span className={`text-sm font-semibold ${(allocations[strategy.code] ?? 0) > 0 ? 'text-brand-accent-green' : 'text-gray-500'}`}>
                      {allocations[strategy.code] ?? 0}%
                    </span>
                  </div>
                </div>

                {/* Slider with brain recommendation marker */}
                <div className="relative">
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={allocations[strategy.code] ?? 0}
                    onChange={(e) => handleAllocationChange(strategy.code, parseFloat(e.target.value))}
                    disabled={isAutoMode}
                    className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  />
                  {/* Brain recommendation marker */}
                  {brainAlloc !== undefined && (
                    <div
                      className="absolute top-0 w-1 h-2 bg-purple-400 rounded-full pointer-events-none"
                      style={{ left: `${brainAlloc}%` }}
                      title={`Brain recommends: ${brainAlloc}%`}
                    />
                  )}
                </div>

                {/* Fitness Score Bar */}
                {fitness && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 w-16 shrink-0">Fitness</span>
                    <div className="flex-1 h-1.5 bg-gray-700/50 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${Math.min(100, fitness.score * 100)}%`,
                          backgroundColor: color,
                          opacity: 0.7,
                        }}
                      />
                    </div>
                    <span className="text-xs text-gray-500 w-10 text-right">
                      {(fitness.score * 100).toFixed(0)}
                    </span>
                  </div>
                )}

                {/* Fitness Breakdown (compact) */}
                {fitness && (
                  <div className="flex gap-1.5 flex-wrap">
                    {Object.entries(fitness.breakdown).map(([key, data]) => (
                      <span
                        key={key}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400"
                        title={`${key}: ${data.score.toFixed(2)} (weight: ${(data.weight * 100).toFixed(0)}%)`}
                      >
                        {key.replace('_', ' ')}: {(data.score * 100).toFixed(0)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )
          })}

          {/* Total Display */}
          <div className="mt-8 p-4 bg-black/30 rounded-lg border border-gray-700">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Total Allocation</span>
              <span className={`text-lg font-bold ${isValid ? 'text-brand-accent-green' : 'text-brand-accent-red'}`}>
                {Math.round(total)}%
              </span>
            </div>
            {!isValid && (
              <p className="text-xs text-red-400 mt-2">
                Total allocation must not exceed 100%
              </p>
            )}
          </div>

          {/* Error Display */}
          {saveError && (
            <p className="text-xs text-red-400">{saveError}</p>
          )}

          {/* Save Button */}
          {!isAutoMode && (
            <button
              onClick={handleSave}
              disabled={!isValid || isSaving}
              className="w-full btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? 'Saving...' : 'Save Allocations'}
            </button>
          )}

          {isAutoMode && (
            <div className="text-center text-xs text-gray-500 py-2">
              Allocations are managed automatically by the Brain.
              {autoStatus && (
                <span className="block mt-1">
                  {autoStatus.total_rebalances} rebalances performed
                </span>
              )}
            </div>
          )}
        </div>

        {/* Pie Chart */}
        <div className="flex flex-col items-center justify-center gap-4">
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={chartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => `${value}%`} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center text-gray-400">
              <p className="text-sm">No allocations set</p>
            </div>
          )}

          {/* Rebalance History Toggle */}
          {autoStatus && autoStatus.rebalance_history.length > 0 && (
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              {showHistory ? 'Hide' : 'Show'} rebalance history ({autoStatus.rebalance_history.length})
            </button>
          )}
        </div>
      </div>

      {/* Rebalance History */}
      {showHistory && autoStatus && autoStatus.rebalance_history.length > 0 && (
        <div className="space-y-2 pt-4 border-t border-gray-700/50">
          <h4 className="text-sm font-medium text-gray-400">Recent Rebalances</h4>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {[...autoStatus.rebalance_history].reverse().map((event, i) => (
              <div key={i} className="flex items-start gap-3 p-2 bg-gray-800/30 rounded text-xs">
                <span className="text-gray-500 shrink-0 w-12">
                  #{event.rebalance_number}
                </span>
                <div className="flex-1">
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(event.changes).map(([code, change]) => {
                      if (change.delta === 0) return null
                      return (
                        <span
                          key={code}
                          className={change.delta > 0 ? 'text-green-400' : 'text-red-400'}
                        >
                          {code}: {change.delta > 0 ? '+' : ''}{change.delta}%
                        </span>
                      )
                    })}
                  </div>
                </div>
                <span className="text-gray-600 shrink-0">
                  {new Date(event.timestamp).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}
