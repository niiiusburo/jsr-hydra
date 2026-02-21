'use client'

import { useState, useEffect, useCallback } from 'react'
import { Check, TrendingUp, Loader2, Save, AlertCircle } from 'lucide-react'
import { getTradingSymbols, updateTradingSymbols, TradingSymbolsConfig } from '@/lib/api'

// Symbol display info
const SYMBOL_INFO: Record<string, { label: string; flag: string }> = {
  EURUSD: { label: 'EUR/USD', flag: '\u{1F1EA}\u{1F1FA}\u{1F1FA}\u{1F1F8}' },
  GBPUSD: { label: 'GBP/USD', flag: '\u{1F1EC}\u{1F1E7}\u{1F1FA}\u{1F1F8}' },
  USDJPY: { label: 'USD/JPY', flag: '\u{1F1FA}\u{1F1F8}\u{1F1EF}\u{1F1F5}' },
  XAUUSD: { label: 'XAU/USD', flag: '\u{1F947}' },
  BTCUSD: { label: 'BTC/USD', flag: '\u20BF' },
  AUDUSD: { label: 'AUD/USD', flag: '\u{1F1E6}\u{1F1FA}\u{1F1FA}\u{1F1F8}' },
  USDCAD: { label: 'USD/CAD', flag: '\u{1F1FA}\u{1F1F8}\u{1F1E8}\u{1F1E6}' },
  NZDUSD: { label: 'NZD/USD', flag: '\u{1F1F3}\u{1F1FF}\u{1F1FA}\u{1F1F8}' },
}

export function TradingPairSelector() {
  const [config, setConfig] = useState<TradingSymbolsConfig | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [initialSelected, setInitialSelected] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getTradingSymbols()
      setConfig(data)
      setSelected(data.active_symbols)
      setInitialSelected(data.active_symbols)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trading symbols')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchConfig()
  }, [fetchConfig])

  // Clear success message after 3 seconds
  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(false), 3000)
      return () => clearTimeout(timer)
    }
  }, [success])

  const isDirty = JSON.stringify([...selected].sort()) !== JSON.stringify([...initialSelected].sort())

  const toggleSymbol = (symbol: string) => {
    setSelected((prev) =>
      prev.includes(symbol) ? prev.filter((s) => s !== symbol) : [...prev, symbol]
    )
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      setError(null)
      const data = await updateTradingSymbols(selected)
      setConfig(data)
      setSelected(data.active_symbols)
      setInitialSelected(data.active_symbols)
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save changes')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl border border-gray-700/50 bg-[#0d1f3c]/80 p-6 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-[#00d97e]/10 border border-[#00d97e]/20">
          <TrendingUp className="w-5 h-5 text-[#00d97e]" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-gray-100">Trading Pairs</h2>
          <p className="text-sm text-gray-500">Select active symbols for the trading engine</p>
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex flex-col items-center justify-center py-12 gap-3">
          <Loader2 className="w-8 h-8 text-[#00d97e] animate-spin" />
          <p className="text-sm text-gray-500">Loading symbols...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 mb-4 rounded-lg bg-[#e63757]/10 border border-[#e63757]/30">
          <AlertCircle className="w-4 h-4 text-[#e63757] shrink-0" />
          <p className="text-sm text-[#e63757]">{error}</p>
        </div>
      )}

      {/* Success Toast */}
      {success && (
        <div className="flex items-center gap-2 px-4 py-3 mb-4 rounded-lg bg-[#00d97e]/10 border border-[#00d97e]/30">
          <Check className="w-4 h-4 text-[#00d97e] shrink-0" />
          <p className="text-sm text-[#00d97e]">Changes saved successfully</p>
        </div>
      )}

      {/* Symbol Grid */}
      {!loading && config && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
            {config.available_symbols.map((symbol) => {
              const isActive = selected.includes(symbol)
              const info = SYMBOL_INFO[symbol]
              const symbolConfig = config.symbol_configs[symbol]

              return (
                <button
                  key={symbol}
                  onClick={() => toggleSymbol(symbol)}
                  className={`
                    relative flex flex-col items-center gap-1.5 px-4 py-4 rounded-xl border
                    transition-all duration-200 cursor-pointer select-none
                    ${
                      isActive
                        ? 'border-[#00d97e] bg-[#00d97e]/10 text-[#00d97e] shadow-[0_0_15px_rgba(0,217,126,0.15)]'
                        : 'border-gray-700 bg-gray-900/50 text-gray-500 hover:border-gray-600 hover:bg-gray-900/70'
                    }
                  `}
                >
                  {/* Check indicator */}
                  {isActive && (
                    <div className="absolute top-2 right-2">
                      <Check className="w-3.5 h-3.5 text-[#00d97e]" />
                    </div>
                  )}

                  {/* Flag */}
                  <span className="text-2xl leading-none">
                    {info?.flag || symbol.slice(0, 3)}
                  </span>

                  {/* Symbol Name */}
                  <span className={`text-sm font-semibold tracking-wide ${isActive ? 'text-[#00d97e]' : 'text-gray-300'}`}>
                    {info?.label || symbol}
                  </span>

                  {/* Lot Size */}
                  {symbolConfig && (
                    <span className={`text-xs ${isActive ? 'text-[#00d97e]/60' : 'text-gray-600'}`}>
                      Lot: {symbolConfig.lot_size}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Info Note */}
          <p className="text-xs text-gray-600 mb-4 flex items-center gap-1.5">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            Changes take effect on next engine restart
          </p>

          {/* Save Button */}
          <button
            onClick={handleSave}
            disabled={!isDirty || saving}
            className={`
              flex items-center justify-center gap-2 w-full py-3 rounded-xl font-semibold text-sm
              transition-all duration-200
              ${
                isDirty
                  ? 'bg-[#00d97e] text-[#0a1628] hover:bg-[#00d97e]/90 shadow-[0_0_20px_rgba(0,217,126,0.2)]'
                  : 'bg-gray-800 text-gray-600 cursor-not-allowed'
              }
            `}
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </>
      )}
    </div>
  )
}
