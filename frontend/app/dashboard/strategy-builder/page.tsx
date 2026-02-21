'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import {
  Wand2,
  RefreshCw,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Clock,
  Loader2,
} from 'lucide-react'
import {
  parseStrategy,
  refineStrategy,
  getStrategyBuilderHistory,
} from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

interface StrategyCondition {
  type: string
  subject?: { type: string; name?: string; period?: number; field?: string; source?: string }
  reference?: { type: string; name?: string; period?: number; source?: string }
  operator?: string
  value?: number
  value2?: number
  direction?: string
}

interface StrategyDef {
  strategy_id: string
  name: string
  description: string
  action: string
  conditions: StrategyCondition[]
  exit_conditions: StrategyCondition[]
  risk: { sl_atr_mult: number; tp_atr_mult: number }
  suggested_timeframe: string
  confidence: number
  warnings: string[]
  pine_script: string
  python_code: string
  webhook_payload: string
  created_at?: string
  symbol?: string
  refined_from?: string
}

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round((value ?? 0) * 100)
  const color = pct >= 80 ? '#00d97e' : pct >= 60 ? '#f59e0b' : '#ef4444'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-mono" style={{ color }}>{pct}%</span>
    </div>
  )
}

function ConditionPill({ cond, isExit = false }: { cond: StrategyCondition; isExit?: boolean }) {
  const subj = cond.subject
  const ref = cond.reference

  const subjLabel = subj
    ? subj.type === 'price'
      ? (subj.field || 'close').toUpperCase()
      : `${subj.name || ''}${subj.period ? `(${subj.period})` : ''}`
    : '?'

  const refLabel = ref
    ? ref.type === 'value'
      ? String(cond.value ?? '')
      : `${ref.name || ''}${ref.period ? `(${ref.period})` : ''}`
    : cond.value !== undefined
    ? String(cond.value)
    : ''

  const opLabel = (() => {
    if (cond.type === 'crossover' || cond.direction === 'above') return 'crosses above'
    if (cond.type === 'crossunder' || cond.direction === 'below') return 'crosses below'
    if (cond.operator === 'less_than') return '<'
    if (cond.operator === 'greater_than') return '>'
    if (cond.operator === 'between') return 'between'
    if (cond.type === 'slope') return cond.direction === 'rising' ? 'rising' : 'falling'
    return cond.type || '?'
  })()

  const borderColor = isExit ? 'border-orange-500/30' : 'border-[#00d97e]/30'
  const textColor = isExit ? 'text-orange-300' : 'text-[#00d97e]'

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-mono border ${borderColor} bg-gray-900`}
    >
      <span className={textColor}>{subjLabel}</span>
      <span className="text-gray-500">{opLabel}</span>
      {refLabel && <span className={textColor}>{refLabel}</span>}
    </span>
  )
}

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={copy}
      className="flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-gray-200 border border-gray-700 hover:border-gray-500 rounded transition-all"
    >
      {copied ? <Check size={12} className="text-[#00d97e]" /> : <Copy size={12} />}
      {label || (copied ? 'Copied!' : 'Copy')}
    </button>
  )
}

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  return (
    <div className="relative">
      <div className="flex items-center justify-between px-3 py-2 bg-gray-900 border border-gray-700 rounded-t-lg">
        <span className="text-xs text-gray-500 font-mono">{lang}</span>
        <CopyButton text={code} />
      </div>
      <pre className="p-4 bg-black border border-t-0 border-gray-700 rounded-b-lg text-xs text-gray-300 font-mono overflow-x-auto max-h-80 scrollbar-thin">
        <code>{code}</code>
      </pre>
    </div>
  )
}

function CollapsibleSection({
  title,
  children,
  defaultOpen = false,
  badge,
}: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
  badge?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-gray-800 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-900/50 hover:bg-gray-900 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-200">{title}</span>
          {badge && (
            <span className="text-xs px-1.5 py-0.5 bg-gray-800 text-gray-400 rounded font-mono">
              {badge}
            </span>
          )}
        </div>
        {open ? (
          <ChevronDown size={14} className="text-gray-500" />
        ) : (
          <ChevronRight size={14} className="text-gray-500" />
        )}
      </button>
      {open && <div className="p-4 bg-black/30">{children}</div>}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────

const SYMBOLS = ['BTCUSD', 'ETHUSD', 'EURUSD', 'GBPUSD', 'XAUUSD', 'USDJPY', 'NASDAQ', 'SP500']

const EXAMPLE_PROMPTS = [
  'Buy when price crosses above SMA44 and RSI is below 30',
  'Sell when EMA20 crosses below EMA50 and ADX is above 25',
  'Enter long when price touches lower Bollinger Band and RSI is under 35',
  'Buy when MACD line crosses above signal line and price is above EMA200',
  'Short when RSI is above 70 and price is near upper Bollinger Band',
]

export default function StrategyBuilderPage() {
  const router = useRouter()
  const { token } = useAppStore()

  const [input, setInput] = useState('')
  const [symbol, setSymbol] = useState('BTCUSD')
  const [parsing, setParsing] = useState(false)
  const [result, setResult] = useState<StrategyDef | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Refine panel
  const [refineInput, setRefineInput] = useState('')
  const [refining, setRefining] = useState(false)

  // History sidebar
  const [history, setHistory] = useState<any[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleUnauthorized = useCallback(() => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('auth_token')
      localStorage.removeItem('app-store')
    }
    router.replace('/login')
  }, [router])

  const loadHistory = useCallback(async () => {
    try {
      setLoadingHistory(true)
      const items = await getStrategyBuilderHistory()
      setHistory(items || [])
    } catch {
      // History is non-critical
    } finally {
      setLoadingHistory(false)
    }
  }, [])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  const handleParse = async () => {
    if (!input.trim()) return
    setParsing(true)
    setError(null)
    setResult(null)

    try {
      const parsed = await parseStrategy(input.trim(), symbol)
      setResult(parsed)
      await loadHistory()
    } catch (err: any) {
      if (err.message?.includes('401') || err.message?.includes('Unauthorized')) {
        handleUnauthorized()
        return
      }
      setError(err instanceof Error ? err.message : 'Failed to parse strategy')
    } finally {
      setParsing(false)
    }
  }

  const handleRefine = async () => {
    if (!refineInput.trim() || !result?.strategy_id) return
    setRefining(true)
    setError(null)

    try {
      const refined = await refineStrategy(result.strategy_id, refineInput.trim())
      setResult(refined)
      setRefineInput('')
      await loadHistory()
    } catch (err: any) {
      if (err.message?.includes('401') || err.message?.includes('Unauthorized')) {
        handleUnauthorized()
        return
      }
      setError(err instanceof Error ? err.message : 'Failed to refine strategy')
    } finally {
      setRefining(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleParse()
    }
  }

  const loadFromHistory = (item: any) => {
    setInput(item.description?.replace('Generated from: ', '') || '')
    setSymbol(item.symbol || 'BTCUSD')
    setResult(item as StrategyDef)
    setError(null)
  }

  return (
    <div className="min-h-screen bg-brand-dark p-4 md:p-6">
      <div className="max-w-7xl mx-auto">

        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 rounded-lg bg-[#00d97e]/10 border border-[#00d97e]/20">
            <Wand2 size={24} className="text-[#00d97e]" />
          </div>
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-gray-100">Strategy Builder</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Describe a trading strategy in plain English — get Pine Script and Python code instantly
            </p>
          </div>
        </div>

        {/* Main layout: input + results | history sidebar */}
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">

          {/* Left column: input + results */}
          <div className="xl:col-span-3 space-y-4">

            {/* Input panel */}
            <div className="bg-brand-panel border border-gray-700 rounded-lg p-5">
              <div className="flex flex-col sm:flex-row gap-3 mb-4">
                <div className="flex-1">
                  <label className="text-xs text-gray-500 uppercase tracking-wide mb-1 block">
                    Describe your strategy
                  </label>
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={EXAMPLE_PROMPTS[0]}
                    rows={3}
                    className="w-full bg-black border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-100 font-mono placeholder-gray-600 focus:outline-none focus:border-[#00d97e]/50 resize-none"
                  />
                  <p className="text-xs text-gray-600 mt-1">
                    Press Cmd+Enter to parse &bull; Be as specific as possible (indicator names, periods, thresholds)
                  </p>
                </div>

                <div className="sm:w-40">
                  <label className="text-xs text-gray-500 uppercase tracking-wide mb-1 block">
                    Symbol
                  </label>
                  <select
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    className="w-full bg-black border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-[#00d97e]/50"
                  >
                    {SYMBOLS.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Example prompts */}
              <div className="mb-4">
                <p className="text-xs text-gray-600 mb-2">Examples:</p>
                <div className="flex flex-wrap gap-2">
                  {EXAMPLE_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => setInput(prompt)}
                      className="text-xs px-2 py-1 bg-gray-900 text-gray-400 hover:text-gray-200 border border-gray-700 hover:border-gray-500 rounded transition-all truncate max-w-xs"
                    >
                      {prompt.slice(0, 55)}{prompt.length > 55 ? '...' : ''}
                    </button>
                  ))}
                </div>
              </div>

              <button
                onClick={handleParse}
                disabled={!input.trim() || parsing}
                className="flex items-center gap-2 px-6 py-2.5 bg-[#00d97e] text-black font-semibold text-sm rounded-lg hover:bg-[#00c070] disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {parsing ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Parsing...
                  </>
                ) : (
                  <>
                    <Wand2 size={16} />
                    Parse Strategy
                  </>
                )}
              </button>
            </div>

            {/* Error state */}
            {error && (
              <div className="p-4 bg-red-900/20 border border-red-700/50 rounded-lg text-red-400 text-sm flex items-start gap-2">
                <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            {/* Results panel */}
            {result && (
              <div className="space-y-4">

                {/* Strategy header card */}
                <div className="bg-brand-panel border border-[#00d97e]/20 rounded-lg p-5"
                  style={{ boxShadow: '0 0 20px rgba(0,217,126,0.04)' }}
                >
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
                    <div>
                      <h2 className="text-lg font-bold text-gray-100">{result.name}</h2>
                      <p className="text-sm text-gray-400 mt-0.5">{result.description}</p>
                    </div>
                    <div className="flex flex-wrap gap-2 shrink-0">
                      <span className={`px-2 py-1 rounded text-xs font-bold font-mono ${
                        result.action === 'BUY' ? 'bg-[#00d97e]/15 text-[#00d97e]' : 'bg-red-500/15 text-red-400'
                      }`}>
                        {result.action}
                      </span>
                      <span className="px-2 py-1 rounded text-xs font-mono bg-gray-800 text-gray-300">
                        {result.suggested_timeframe}
                      </span>
                      <span className="px-2 py-1 rounded text-xs font-mono bg-gray-800 text-gray-300">
                        {result.symbol}
                      </span>
                    </div>
                  </div>

                  {/* Confidence */}
                  <div className="mb-4">
                    <p className="text-xs text-gray-500 mb-1">Parse confidence</p>
                    <ConfidenceBar value={result.confidence ?? 0} />
                  </div>

                  {/* Entry conditions */}
                  {result.conditions?.length > 0 && (
                    <div className="mb-3">
                      <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Entry conditions</p>
                      <div className="flex flex-wrap gap-2">
                        {result.conditions.map((c, i) => (
                          <ConditionPill key={i} cond={c} />
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Exit conditions */}
                  {result.exit_conditions?.length > 0 && (
                    <div className="mb-3">
                      <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Exit conditions</p>
                      <div className="flex flex-wrap gap-2">
                        {result.exit_conditions.map((c, i) => (
                          <ConditionPill key={i} cond={c} isExit />
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Risk params */}
                  <div className="flex gap-4 text-xs font-mono text-gray-400">
                    <span>SL: <span className="text-gray-200">{result.risk?.sl_atr_mult ?? 1.5}x ATR</span></span>
                    <span>TP: <span className="text-gray-200">{result.risk?.tp_atr_mult ?? 2.0}x ATR</span></span>
                    <span>R:R: <span className="text-gray-200">
                      1:{((result.risk?.tp_atr_mult ?? 2.0) / (result.risk?.sl_atr_mult ?? 1.5)).toFixed(2)}
                    </span></span>
                  </div>

                  {/* Warnings */}
                  {result.warnings?.length > 0 && (
                    <div className="mt-4 space-y-1">
                      {result.warnings.map((w, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs text-amber-400">
                          <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                          <span>{w}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Code sections */}
                <CollapsibleSection
                  title="Pine Script v5"
                  defaultOpen={true}
                  badge="TradingView"
                >
                  {result.pine_script ? (
                    <CodeBlock code={result.pine_script} lang="pine" />
                  ) : (
                    <p className="text-xs text-gray-500">No Pine Script generated.</p>
                  )}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Python Rule"
                  defaultOpen={false}
                  badge="pandas-ta"
                >
                  {result.python_code ? (
                    <CodeBlock code={result.python_code} lang="python" />
                  ) : (
                    <p className="text-xs text-gray-500">No Python code generated.</p>
                  )}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Webhook Payload Template"
                  defaultOpen={false}
                  badge="JSON"
                >
                  {result.webhook_payload ? (
                    <CodeBlock code={result.webhook_payload} lang="json" />
                  ) : (
                    <p className="text-xs text-gray-500">No webhook payload generated.</p>
                  )}
                </CollapsibleSection>

                {/* Refine panel */}
                <div className="bg-brand-panel border border-gray-700 rounded-lg p-5">
                  <h3 className="text-sm font-semibold text-gray-200 mb-3">
                    Refine this strategy
                  </h3>
                  <div className="flex gap-3">
                    <input
                      type="text"
                      value={refineInput}
                      onChange={(e) => setRefineInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleRefine()}
                      placeholder='e.g. "also add EMA20 filter and tighten SL to 1.2 ATR"'
                      className="flex-1 bg-black border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-[#00d97e]/50 font-mono"
                    />
                    <button
                      onClick={handleRefine}
                      disabled={!refineInput.trim() || refining}
                      className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 text-gray-200 border border-gray-600 hover:border-[#00d97e]/50 hover:text-[#00d97e] text-sm font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                    >
                      {refining ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <RefreshCw size={14} />
                      )}
                      {refining ? 'Refining...' : 'Refine'}
                    </button>
                  </div>
                </div>

                {/* Deploy button (future) */}
                <div className="flex items-center justify-end">
                  <div className="relative group">
                    <button
                      disabled
                      className="flex items-center gap-2 px-5 py-2.5 bg-gray-800 text-gray-500 border border-gray-700 text-sm font-medium rounded-lg cursor-not-allowed"
                    >
                      <Wand2 size={14} />
                      Deploy as Live Strategy
                    </button>
                    <div className="absolute right-0 bottom-full mb-2 hidden group-hover:block z-10">
                      <div className="bg-gray-800 text-gray-300 text-xs px-3 py-2 rounded border border-gray-700 whitespace-nowrap">
                        Coming soon — full engine integration in Phase 3
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right sidebar: history */}
          <div className="xl:col-span-1">
            <div className="bg-brand-panel border border-gray-700 rounded-lg p-4 sticky top-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-300">Recent Strategies</h3>
                <button
                  onClick={loadHistory}
                  disabled={loadingHistory}
                  className="p-1 text-gray-500 hover:text-gray-300 transition-colors"
                >
                  <RefreshCw size={12} className={loadingHistory ? 'animate-spin' : ''} />
                </button>
              </div>

              {history.length === 0 ? (
                <p className="text-xs text-gray-600 text-center py-6">
                  No strategies yet.<br />Parse your first one above.
                </p>
              ) : (
                <div className="space-y-2 max-h-[70vh] overflow-y-auto scrollbar-thin pr-1">
                  {history.map((item) => (
                    <button
                      key={item.strategy_id}
                      onClick={() => loadFromHistory(item)}
                      className={`w-full text-left p-3 rounded-lg border transition-all ${
                        result?.strategy_id === item.strategy_id
                          ? 'border-[#00d97e]/40 bg-[#00d97e]/5'
                          : 'border-gray-800 hover:border-gray-600 bg-gray-900/30 hover:bg-gray-900/50'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-1 mb-1">
                        <p className="text-xs font-medium text-gray-200 leading-tight line-clamp-2">
                          {item.name}
                        </p>
                        <span className={`shrink-0 text-xs font-bold px-1.5 py-0.5 rounded font-mono ${
                          item.action === 'BUY'
                            ? 'bg-[#00d97e]/15 text-[#00d97e]'
                            : 'bg-red-500/15 text-red-400'
                        }`}>
                          {item.action}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-gray-500">
                        <Clock size={10} />
                        <span>{item.suggested_timeframe}</span>
                        <span>&bull;</span>
                        <span>{item.conditions_count} cond.</span>
                        {item.warnings?.length > 0 && (
                          <>
                            <span>&bull;</span>
                            <AlertTriangle size={10} className="text-amber-500" />
                          </>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <style jsx global>{`
        .scrollbar-thin::-webkit-scrollbar {
          width: 4px;
        }
        .scrollbar-thin::-webkit-scrollbar-track {
          background: transparent;
        }
        .scrollbar-thin::-webkit-scrollbar-thumb {
          background: #374151;
          border-radius: 2px;
        }
        .scrollbar-thin::-webkit-scrollbar-thumb:hover {
          background: #4b5563;
        }
        .line-clamp-2 {
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
      `}</style>
    </div>
  )
}
