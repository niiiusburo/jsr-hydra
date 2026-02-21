'use client'

import React, { useState, useEffect, useCallback } from 'react'
import {
  Settings,
  TrendingUp,
  Brain,
  Shield,
  PieChart,
  Cpu,
  Save,
  RotateCcw,
  Check,
  AlertCircle,
  Loader2,
  X,
} from 'lucide-react'
import { TradingPairSelector } from '@/components/settings/TradingPairSelector'
import { LLMModelSelector } from '@/components/settings/LLMModelSelector'
import { LearningControls } from '@/components/settings/LearningControls'
import { RiskControls } from '@/components/settings/RiskControls'
import { AllocationControls } from '@/components/settings/AllocationControls'
import { StrategyRegimeMatrix } from '@/components/settings/StrategyRegimeMatrix'
import {
  getRuntimeSettings,
  updateRuntimeSettings,
  resetRuntimeSettings,
  RuntimeSettings,
} from '@/lib/api'

// ─────────────────────────────────────────────────────────────
// Tabs definition
// ─────────────────────────────────────────────────────────────
type TabKey = 'trading' | 'learning' | 'risk' | 'allocation' | 'brain'

const TABS: { key: TabKey; label: string; icon: React.ReactNode }[] = [
  { key: 'trading', label: 'Trading', icon: <TrendingUp size={15} /> },
  { key: 'learning', label: 'Learning', icon: <Brain size={15} /> },
  { key: 'risk', label: 'Risk', icon: <Shield size={15} /> },
  { key: 'allocation', label: 'Allocation', icon: <PieChart size={15} /> },
  { key: 'brain', label: 'AI Brain', icon: <Cpu size={15} /> },
]

// ─────────────────────────────────────────────────────────────
// Default settings (used as fallback when API not yet ready)
// ─────────────────────────────────────────────────────────────
const DEFAULT_SETTINGS: RuntimeSettings = {
  learning: {
    exploration_rate: 10,
    min_trades_for_adjustment: 5,
    max_trade_history: 500,
    streak_warning_threshold: 3,
    confidence_lookback: 20,
    learning_speed: 'normal',
    automation_level: 'semi_auto',
  },
  allocator: {
    rebalance_interval: 10,
    max_change_per_rebalance: 5,
    min_allocation_pct: 5,
    max_allocation_pct: 40,
  },
  risk: {
    max_drawdown_pct: 15,
    daily_loss_limit_pct: 3,
    per_trade_risk_pct: 1.0,
    max_lots: 1.0,
  },
  patterns: {
    hour_filter_enabled: true,
    dow_filter_enabled: true,
    min_trades_for_pattern: 10,
  },
  exploration_decay: {
    exploration_decay_enabled: false,
    exploration_decay_after_trades: 200,
    exploration_decay_target: 3,
  },
}

// ─────────────────────────────────────────────────────────────
// Toast banner component
// ─────────────────────────────────────────────────────────────
function Toast({
  type,
  message,
  onDismiss,
}: {
  type: 'success' | 'error'
  message: string
  onDismiss: () => void
}) {
  return (
    <div
      className={`
        flex items-center gap-3 px-4 py-3 rounded-lg border mb-6
        ${type === 'success'
          ? 'bg-[#00d97e]/10 border-[#00d97e]/30 text-[#00d97e]'
          : 'bg-[#e63757]/10 border-[#e63757]/30 text-[#e63757]'
        }
      `}
    >
      {type === 'success'
        ? <Check className="w-4 h-4 shrink-0" />
        : <AlertCircle className="w-4 h-4 shrink-0" />
      }
      <p className="text-sm flex-1">{message}</p>
      <button onClick={onDismiss} className="opacity-60 hover:opacity-100 transition-opacity">
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Confirm dialog
// ─────────────────────────────────────────────────────────────
function ConfirmDialog({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-[#0d1117] border border-gray-700 rounded-xl p-6 max-w-sm w-full mx-4 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <RotateCcw className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h3 className="text-base font-bold text-gray-100">Reset to Defaults?</h3>
            <p className="text-xs text-gray-500 mt-0.5">This action cannot be undone</p>
          </div>
        </div>
        <p className="text-sm text-gray-400 mb-6">
          All runtime settings will be reset to factory defaults. Your trading pair and LLM
          settings will not be affected.
        </p>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-2.5 rounded-xl border border-gray-700 text-gray-300 text-sm font-medium hover:bg-gray-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 py-2.5 rounded-xl bg-amber-500/20 border border-amber-500/30 text-amber-300 text-sm font-medium hover:bg-amber-500/30 transition-colors"
          >
            Reset All
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Main settings page
// ─────────────────────────────────────────────────────────────
export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('trading')
  const [settings, setSettings] = useState<RuntimeSettings>(DEFAULT_SETTINGS)
  const [dirtySettings, setDirtySettings] = useState<Partial<any>>({})
  const [isDirty, setIsDirty] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  // Strategy regime blacklist state (separate from runtime settings)
  const [blacklist, setBlacklist] = useState<Record<string, string[]>>({})

  // Auto-allocation toggle (lives outside RuntimeSettings for UI clarity)
  const [autoAlloc, setAutoAlloc] = useState(true)

  // ── Dismiss toast automatically ──────────────────────────────
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 4000)
      return () => clearTimeout(timer)
    }
  }, [toast])

  // ── Fetch runtime settings on mount ──────────────────────────
  const fetchSettings = useCallback(async () => {
    try {
      setLoading(true)
      const data = await getRuntimeSettings()
      setSettings(data)
      setDirtySettings({})
      setIsDirty(false)
    } catch {
      // API not wired yet — keep defaults, don't crash
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSettings()
  }, [fetchSettings])

  // ── Generic nested change handler ────────────────────────────
  const handleChange = (section: keyof RuntimeSettings) => (key: string, value: any) => {
    setSettings((prev) => ({
      ...prev,
      [section]: { ...prev[section], [key]: value },
    }))
    setDirtySettings((prev) => ({
      ...prev,
      [section]: { ...(prev[section] || {}), [key]: value },
    }))
    setIsDirty(true)
  }

  // ── Blacklist toggle ─────────────────────────────────────────
  const handleBlacklistChange = (strategy: string, regime: string, enable: boolean) => {
    setBlacklist((prev) => {
      const current = prev[strategy] || []
      const updated = enable
        ? current.filter((r) => r !== regime)
        : [...current, regime]
      return { ...prev, [strategy]: updated }
    })
    setIsDirty(true)
  }

  // ── Save ─────────────────────────────────────────────────────
  const handleSave = async () => {
    try {
      setSaving(true)
      const updated = await updateRuntimeSettings(dirtySettings)
      setSettings(updated)
      setDirtySettings({})
      setIsDirty(false)
      setToast({ type: 'success', message: 'Settings saved successfully' })
    } catch (err) {
      setToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to save settings',
      })
    } finally {
      setSaving(false)
    }
  }

  // ── Reset ─────────────────────────────────────────────────────
  const handleReset = async () => {
    setShowConfirm(false)
    try {
      setSaving(true)
      const defaults = await resetRuntimeSettings()
      setSettings(defaults)
      setDirtySettings({})
      setIsDirty(false)
      setBlacklist({})
      setToast({ type: 'success', message: 'Settings reset to factory defaults' })
    } catch (err) {
      setToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to reset settings',
      })
    } finally {
      setSaving(false)
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0a0a] p-4 md:p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-lg bg-[#00d97e]/10 border border-[#00d97e]/20 flex items-center justify-center">
            <Settings className="w-5 h-5 text-[#00d97e]" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-100">Settings</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Configure engine behaviour, risk limits, and AI parameters
            </p>
          </div>
          {loading && (
            <div className="ml-auto flex items-center gap-2 text-sm text-gray-500">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading...
            </div>
          )}
        </div>

        {/* Toast */}
        {toast && (
          <Toast type={toast.type} message={toast.message} onDismiss={() => setToast(null)} />
        )}

        {/* Tab Bar */}
        <div className="flex gap-1 p-1 bg-gray-900/60 border border-gray-800 rounded-xl mb-6 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`
                flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-150 whitespace-nowrap flex-shrink-0
                ${activeTab === tab.key
                  ? 'bg-[#00d97e]/10 text-[#00d97e] border border-[#00d97e]/30'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
                }
              `}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="mb-8">

          {/* ── Trading ── */}
          {activeTab === 'trading' && (
            <div className="space-y-6">
              <TradingPairSelector />
              <StrategyRegimeMatrix
                blacklist={blacklist}
                onChange={handleBlacklistChange}
              />
            </div>
          )}

          {/* ── Learning ── */}
          {activeTab === 'learning' && !loading && (
            <LearningControls
              settings={settings.learning}
              onChange={handleChange('learning')}
            />
          )}

          {/* ── Risk ── */}
          {activeTab === 'risk' && !loading && (
            <RiskControls
              settings={settings.risk}
              onChange={handleChange('risk')}
            />
          )}

          {/* ── Allocation ── */}
          {activeTab === 'allocation' && !loading && (
            <AllocationControls
              settings={settings.allocator}
              onChange={handleChange('allocator')}
              autoEnabled={autoAlloc}
              onAutoToggle={setAutoAlloc}
            />
          )}

          {/* ── AI Brain ── */}
          {activeTab === 'brain' && (
            <LLMModelSelector />
          )}

          {/* Loading skeleton for data tabs */}
          {loading && activeTab !== 'trading' && activeTab !== 'brain' && (
            <div className="rounded-xl border border-gray-700/50 bg-[#0d1117]/80 p-6">
              <div className="space-y-4 animate-pulse">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-10 bg-gray-800 rounded-lg" />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Bottom Action Bar */}
        {activeTab !== 'trading' && activeTab !== 'brain' && (
          <div className="flex items-center justify-between gap-4 pt-4 border-t border-gray-800">
            <button
              onClick={() => setShowConfirm(true)}
              disabled={saving}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-gray-700 text-gray-400 text-sm font-medium hover:border-gray-600 hover:text-gray-200 transition-all duration-150 disabled:opacity-50"
            >
              <RotateCcw className="w-4 h-4" />
              Reset to Defaults
            </button>

            <button
              onClick={handleSave}
              disabled={!isDirty || saving}
              className={`
                flex items-center gap-2 px-6 py-2.5 rounded-xl font-semibold text-sm transition-all duration-150
                ${isDirty && !saving
                  ? 'bg-[#00d97e] text-[#0a1628] hover:bg-[#00d97e]/90 shadow-[0_0_20px_rgba(0,217,126,0.2)]'
                  : 'bg-gray-800 text-gray-600 cursor-not-allowed'
                }
              `}
            >
              {saving
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Save className="w-4 h-4" />
              }
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        )}
      </div>

      {/* Confirm Reset Dialog */}
      {showConfirm && (
        <ConfirmDialog
          onConfirm={handleReset}
          onCancel={() => setShowConfirm(false)}
        />
      )}

      {/* Slider thumb styles */}
      <style jsx global>{`
        input[type='range']::-webkit-slider-thumb {
          -webkit-appearance: none;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: #00d97e;
          cursor: pointer;
          border: 2px solid #0a0a0a;
          box-shadow: 0 0 6px rgba(0, 217, 126, 0.4);
          transition: box-shadow 0.15s;
        }
        input[type='range']::-webkit-slider-thumb:hover {
          box-shadow: 0 0 10px rgba(0, 217, 126, 0.6);
        }
        input[type='range']::-moz-range-thumb {
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: #00d97e;
          cursor: pointer;
          border: 2px solid #0a0a0a;
        }
      `}</style>
    </div>
  )
}
