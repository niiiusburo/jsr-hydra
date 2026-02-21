'use client'

import React from 'react'
import { AlertTriangle, ShieldAlert } from 'lucide-react'
import { RuntimeSettings } from '@/lib/api'

interface RiskControlsProps {
  settings: RuntimeSettings['risk']
  onChange: (key: string, value: any) => void
}

function RiskSlider({
  label,
  description,
  value,
  min,
  max,
  step,
  format,
  danger,
  warning,
  onChange,
}: {
  label: string
  description: string
  value: number
  min: number
  max: number
  step: number
  format: (v: number) => string
  danger?: boolean
  warning?: boolean
  onChange: (v: number) => void
}) {
  const pct = ((value - min) / (max - min)) * 100
  const accentColor = danger ? '#e63757' : warning ? '#f59e0b' : '#00d97e'
  const trackColor = danger
    ? `linear-gradient(to right, #e63757 ${pct}%, #1f2937 ${pct}%)`
    : warning
      ? `linear-gradient(to right, #f59e0b ${pct}%, #1f2937 ${pct}%)`
      : `linear-gradient(to right, #00d97e ${pct}%, #1f2937 ${pct}%)`

  return (
    <div className="py-4 border-b border-gray-800 last:border-0">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-200">{label}</span>
          {danger && <ShieldAlert className="w-3.5 h-3.5 text-[#e63757]" />}
          {warning && !danger && <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />}
        </div>
        <span
          className="text-sm font-mono tabular-nums"
          style={{ color: accentColor }}
        >
          {format(value)}
        </span>
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
        style={{ background: trackColor }}
      />
      <div className="flex justify-between mt-1">
        <span className="text-xs text-gray-600">{format(min)}</span>
        <span className="text-xs text-gray-600">{format(max)}</span>
      </div>
    </div>
  )
}

export function RiskControls({ settings, onChange }: RiskControlsProps) {
  const drawdownDanger = settings.max_drawdown_pct > 20

  return (
    <div className="rounded-xl border border-gray-700/50 bg-[#0d1117]/80 p-6 backdrop-blur-sm">
      <div className="mb-5">
        <h2 className="text-lg font-bold text-gray-100">Risk Management</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Hard limits that protect the account from excessive losses
        </p>
      </div>

      {drawdownDanger && (
        <div className="flex items-center gap-2 px-4 py-3 mb-4 rounded-lg bg-[#e63757]/10 border border-[#e63757]/30">
          <AlertTriangle className="w-4 h-4 text-[#e63757] shrink-0" />
          <p className="text-sm text-[#e63757]">
            Max drawdown above 20% — high risk to account equity
          </p>
        </div>
      )}

      <RiskSlider
        label="Max Drawdown %"
        description="Engine halts trading when account drawdown exceeds this threshold"
        value={settings.max_drawdown_pct}
        min={5}
        max={30}
        step={1}
        format={(v) => `${v}%`}
        danger={drawdownDanger}
        warning={settings.max_drawdown_pct > 15 && !drawdownDanger}
        onChange={(v) => onChange('max_drawdown_pct', v)}
      />

      <RiskSlider
        label="Daily Loss Limit %"
        description="Trading is suspended for the day when daily P&L drops below this percentage"
        value={settings.daily_loss_limit_pct}
        min={1}
        max={10}
        step={0.5}
        format={(v) => `${v}%`}
        warning={settings.daily_loss_limit_pct > 7}
        onChange={(v) => onChange('daily_loss_limit_pct', v)}
      />

      <RiskSlider
        label="Per-Trade Risk %"
        description="Maximum account equity risked on any single trade (stop-loss sizing)"
        value={settings.per_trade_risk_pct}
        min={0.25}
        max={3.0}
        step={0.25}
        format={(v) => `${v.toFixed(2)}%`}
        warning={settings.per_trade_risk_pct > 2}
        onChange={(v) => onChange('per_trade_risk_pct', v)}
      />

      <div className="py-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm font-medium text-gray-200">Max Lots</span>
          <span className="text-sm font-mono text-[#00d97e] tabular-nums">
            {settings.max_lots.toFixed(2)}
          </span>
        </div>
        <p className="text-xs text-gray-500 mb-3">
          Maximum lot size allowed per trade regardless of signal strength
        </p>
        <input
          type="number"
          min={0.01}
          max={10.0}
          step={0.01}
          value={settings.max_lots}
          onChange={(e) => onChange('max_lots', Number(e.target.value))}
          className="
            w-full px-4 py-2.5 rounded-lg
            bg-gray-900/70 border border-gray-700 text-gray-200
            text-sm font-mono
            focus:outline-none focus:border-[#00d97e]/50 focus:ring-1 focus:ring-[#00d97e]/20
            transition-all duration-200
          "
        />
        <div className="flex justify-between mt-1">
          <span className="text-xs text-gray-600">Min: 0.01</span>
          <span className="text-xs text-gray-600">Max: 10.00</span>
        </div>
      </div>
    </div>
  )
}
