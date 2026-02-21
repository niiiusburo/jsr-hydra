'use client'

import React from 'react'
import { RuntimeSettings } from '@/lib/api'

interface LearningControlsProps {
  settings: RuntimeSettings['learning']
  onChange: (key: string, value: any) => void
}

function SliderRow({
  label,
  description,
  value,
  min,
  max,
  step = 1,
  format,
  onChange,
}: {
  label: string
  description: string
  value: number
  min: number
  max: number
  step?: number
  format?: (v: number) => string
  onChange: (v: number) => void
}) {
  const display = format ? format(value) : String(value)
  const pct = ((value - min) / (max - min)) * 100

  return (
    <div className="py-4 border-b border-gray-800 last:border-0">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-gray-200">{label}</span>
        <span className="text-sm font-mono text-[#00d97e] tabular-nums">{display}</span>
      </div>
      <p className="text-xs text-gray-500 mb-3">{description}</p>
      <div className="relative">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full h-1.5 appearance-none rounded-full bg-gray-800 cursor-pointer"
          style={{
            background: `linear-gradient(to right, #00d97e ${pct}%, #1f2937 ${pct}%)`,
          }}
        />
        <div className="flex justify-between mt-1">
          <span className="text-xs text-gray-600">{format ? format(min) : min}</span>
          <span className="text-xs text-gray-600">{format ? format(max) : max}</span>
        </div>
      </div>
    </div>
  )
}

function ChipGroup({
  label,
  description,
  options,
  value,
  onChange,
}: {
  label: string
  description: string
  options: { value: string; label: string }[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="py-4 border-b border-gray-800 last:border-0">
      <div className="mb-1">
        <span className="text-sm font-medium text-gray-200">{label}</span>
      </div>
      <p className="text-xs text-gray-500 mb-3">{description}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => {
          const isActive = value === opt.value
          return (
            <button
              key={opt.value}
              onClick={() => onChange(opt.value)}
              className={`
                px-4 py-1.5 rounded-lg border text-sm font-medium transition-all duration-150 select-none
                ${isActive
                  ? 'border-[#00d97e] bg-[#00d97e]/10 text-[#00d97e] shadow-[0_0_8px_rgba(0,217,126,0.15)]'
                  : 'border-gray-700 bg-gray-900/50 text-gray-400 hover:border-gray-600 hover:text-gray-300'
                }
              `}
            >
              {opt.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function LearningControls({ settings, onChange }: LearningControlsProps) {
  return (
    <div className="rounded-xl border border-gray-700/50 bg-[#0d1117]/80 p-6 backdrop-blur-sm">
      <div className="mb-5">
        <h2 className="text-lg font-bold text-gray-100">Learning Parameters</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Control how the engine learns from trade history and adapts strategies
        </p>
      </div>

      <ChipGroup
        label="Learning Speed"
        description="How aggressively the engine adjusts strategy weights after each trade"
        options={[
          { value: 'conservative', label: 'Conservative' },
          { value: 'normal', label: 'Normal' },
          { value: 'aggressive', label: 'Aggressive' },
        ]}
        value={settings.learning_speed}
        onChange={(v) => onChange('learning_speed', v)}
      />

      <ChipGroup
        label="Automation Level"
        description="How much autonomy the engine has to act on learned signals"
        options={[
          { value: 'monitor', label: 'Monitor Only' },
          { value: 'suggest', label: 'Suggest' },
          { value: 'semi_auto', label: 'Semi-Auto' },
          { value: 'full_auto', label: 'Full Auto' },
        ]}
        value={settings.automation_level}
        onChange={(v) => onChange('automation_level', v)}
      />

      <SliderRow
        label="Exploration Rate"
        description="Probability of trying a non-optimal strategy to discover new patterns"
        value={settings.exploration_rate}
        min={1}
        max={30}
        step={1}
        format={(v) => `${v}%`}
        onChange={(v) => onChange('exploration_rate', v)}
      />

      <SliderRow
        label="Min Trades for Adjustment"
        description="Minimum number of trades before the engine recalculates strategy weights"
        value={settings.min_trades_for_adjustment}
        min={3}
        max={20}
        onChange={(v) => onChange('min_trades_for_adjustment', v)}
      />

      <SliderRow
        label="Trade History Window"
        description="Number of past trades used for learning and confidence calculations"
        value={settings.max_trade_history}
        min={50}
        max={2000}
        step={50}
        onChange={(v) => onChange('max_trade_history', v)}
      />

      <SliderRow
        label="Confidence Lookback"
        description="Number of recent trades used to calculate per-strategy confidence score"
        value={settings.confidence_lookback}
        min={10}
        max={50}
        onChange={(v) => onChange('confidence_lookback', v)}
      />

      <SliderRow
        label="Streak Warning Threshold"
        description="Number of consecutive losses before a streak warning is triggered"
        value={settings.streak_warning_threshold}
        min={2}
        max={8}
        onChange={(v) => onChange('streak_warning_threshold', v)}
      />
    </div>
  )
}
