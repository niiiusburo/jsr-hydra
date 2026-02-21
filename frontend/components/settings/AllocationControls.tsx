'use client'

import React from 'react'
import { RuntimeSettings } from '@/lib/api'

interface AllocationControlsProps {
  settings: RuntimeSettings['allocator']
  onChange: (key: string, value: any) => void
  autoEnabled?: boolean
  onAutoToggle?: (v: boolean) => void
}

function AllocSlider({
  label,
  description,
  value,
  min,
  max,
  step,
  format,
  onChange,
}: {
  label: string
  description: string
  value: number
  min: number
  max: number
  step: number
  format: (v: number) => string
  onChange: (v: number) => void
}) {
  const pct = ((value - min) / (max - min)) * 100

  return (
    <div className="py-4 border-b border-gray-800 last:border-0">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-gray-200">{label}</span>
        <span className="text-sm font-mono text-[#00d97e] tabular-nums">{format(value)}</span>
      </div>
      <p className="text-xs text-gray-500 mb-3">{description}</p>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 appearance-none rounded-full cursor-pointer"
        style={{
          background: `linear-gradient(to right, #00d97e ${pct}%, #1f2937 ${pct}%)`,
        }}
      />
      <div className="flex justify-between mt-1">
        <span className="text-xs text-gray-600">{format(min)}</span>
        <span className="text-xs text-gray-600">{format(max)}</span>
      </div>
    </div>
  )
}

export function AllocationControls({
  settings,
  onChange,
  autoEnabled = true,
  onAutoToggle,
}: AllocationControlsProps) {
  const minPct = settings.min_allocation_pct
  const maxPct = settings.max_allocation_pct
  const rangeWarning = minPct >= maxPct

  return (
    <div className="rounded-xl border border-gray-700/50 bg-[#0d1117]/80 p-6 backdrop-blur-sm">
      <div className="mb-5">
        <h2 className="text-lg font-bold text-gray-100">Strategy Allocation</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Configure how capital is distributed across active strategies
        </p>
      </div>

      {/* Auto-Allocation Toggle */}
      <div className="py-4 border-b border-gray-800">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm font-medium text-gray-200">Auto-Allocation</span>
            <p className="text-xs text-gray-500 mt-0.5">
              Engine automatically rebalances strategy weights based on performance
            </p>
          </div>
          <button
            onClick={() => onAutoToggle?.(!autoEnabled)}
            className={`
              relative w-12 h-6 rounded-full border transition-all duration-200 focus:outline-none
              ${autoEnabled
                ? 'bg-[#00d97e]/20 border-[#00d97e]/60'
                : 'bg-gray-800 border-gray-700'
              }
            `}
            role="switch"
            aria-checked={autoEnabled}
          >
            <span
              className={`
                absolute top-0.5 left-0.5 w-5 h-5 rounded-full transition-all duration-200
                ${autoEnabled ? 'translate-x-6 bg-[#00d97e]' : 'translate-x-0 bg-gray-500'}
              `}
            />
          </button>
        </div>
      </div>

      {rangeWarning && (
        <div className="mt-4 px-4 py-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
          <p className="text-sm text-amber-400">
            Min allocation must be less than Max allocation
          </p>
        </div>
      )}

      <AllocSlider
        label="Rebalance Interval"
        description="Number of trades between automatic strategy weight recalculations"
        value={settings.rebalance_interval}
        min={5}
        max={50}
        step={5}
        format={(v) => `${v} trades`}
        onChange={(v) => onChange('rebalance_interval', v)}
      />

      <AllocSlider
        label="Max Change Per Rebalance"
        description="Maximum allocation shift allowed in a single rebalance cycle"
        value={settings.max_change_per_rebalance}
        min={1}
        max={20}
        step={1}
        format={(v) => `${v}%`}
        onChange={(v) => onChange('max_change_per_rebalance', v)}
      />

      <AllocSlider
        label="Min Allocation Per Strategy"
        description="Floor allocation — no active strategy will receive less than this"
        value={settings.min_allocation_pct}
        min={1}
        max={15}
        step={1}
        format={(v) => `${v}%`}
        onChange={(v) => onChange('min_allocation_pct', v)}
      />

      <AllocSlider
        label="Max Allocation Per Strategy"
        description="Ceiling allocation — no single strategy can dominate beyond this limit"
        value={settings.max_allocation_pct}
        min={20}
        max={80}
        step={5}
        format={(v) => `${v}%`}
        onChange={(v) => onChange('max_allocation_pct', v)}
      />
    </div>
  )
}
