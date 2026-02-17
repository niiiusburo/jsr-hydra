'use client'

import { useState, useEffect } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts'
import { Card } from '@/components/ui/Card'

interface AllocationManagerProps {
  onSave?: (allocations: Record<string, number>) => void
}

const STRATEGIES = [
  { code: 'STRATEGY_A', name: 'Strategy A', color: '#00d97e' },
  { code: 'STRATEGY_B', name: 'Strategy B', color: '#3b82f6' },
  { code: 'STRATEGY_C', name: 'Strategy C', color: '#f59e0b' },
  { code: 'STRATEGY_D', name: 'Strategy D', color: '#ef4444' },
]

export function AllocationManager({ onSave }: AllocationManagerProps) {
  const [allocations, setAllocations] = useState<Record<string, number>>({
    STRATEGY_A: 25,
    STRATEGY_B: 25,
    STRATEGY_C: 25,
    STRATEGY_D: 25,
  })
  const [isSaving, setIsSaving] = useState(false)

  const total = Object.values(allocations).reduce((sum, val) => sum + val, 0)
  const isValid = total <= 100

  const handleAllocationChange = (code: string, value: number) => {
    setAllocations({
      ...allocations,
      [code]: Math.max(0, Math.min(100, value)),
    })
  }

  const handleSave = async () => {
    if (!isValid) return

    setIsSaving(true)
    try {
      // Call API for each strategy
      for (const [code, value] of Object.entries(allocations)) {
        const response = await fetch(`/api/strategies/${code}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ allocation: value }),
        })
        if (!response.ok) throw new Error(`Failed to update ${code}`)
      }
      onSave?.(allocations)
    } catch (error) {
      console.error('Failed to save allocations:', error)
    } finally {
      setIsSaving(false)
    }
  }

  const chartData = STRATEGIES.filter(s => allocations[s.code] > 0).map(s => ({
    name: s.name,
    value: allocations[s.code],
    color: s.color,
  }))

  return (
    <Card title="Allocation Manager" className="space-y-6">
      <div className="grid md:grid-cols-2 gap-8">
        {/* Sliders */}
        <div className="space-y-6">
          {STRATEGIES.map(strategy => (
            <div key={strategy.code} className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-gray-300">
                  {strategy.name}
                </label>
                <span className={`text-sm font-semibold ${allocations[strategy.code] > 0 ? 'text-brand-accent-green' : 'text-gray-500'}`}>
                  {allocations[strategy.code]}%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={allocations[strategy.code]}
                onChange={(e) => handleAllocationChange(strategy.code, parseFloat(e.target.value))}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer"
              />
            </div>
          ))}

          {/* Total Display */}
          <div className="mt-8 p-4 bg-black/30 rounded-lg border border-gray-700">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Total Allocation</span>
              <span className={`text-lg font-bold ${isValid ? 'text-brand-accent-green' : 'text-brand-accent-red'}`}>
                {total}%
              </span>
            </div>
            {!isValid && (
              <p className="text-xs text-red-400 mt-2">
                Total allocation must not exceed 100%
              </p>
            )}
          </div>

          {/* Save Button */}
          <button
            onClick={handleSave}
            disabled={!isValid || isSaving}
            className="w-full btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? 'Saving...' : 'Save Allocations'}
          </button>
        </div>

        {/* Pie Chart */}
        <div className="flex items-center justify-center">
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
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
        </div>
      </div>
    </Card>
  )
}
