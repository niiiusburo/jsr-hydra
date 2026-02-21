'use client'

import React, { useCallback, useRef, useState } from 'react'
import {
  AlertCircle,
  Camera,
  ChevronRight,
  Clock,
  Eye,
  Loader2,
  RefreshCw,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Minus,
} from 'lucide-react'
import { analyzeChart, getChartVisionHistory } from '@/lib/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Indicator {
  name: string
  period?: number
  color?: string
  current_value?: string
}

interface Pattern {
  pattern: string
  description: string
}

interface KeyLevels {
  support?: number[]
  resistance?: number[]
}

interface SuggestedStrategy {
  action?: string
  reasoning?: string
  entry_condition?: string
  stop_loss?: string
  take_profit?: string
  indicators_to_watch?: string[]
}

interface ChartAnalysis {
  symbol?: string
  timeframe?: string
  indicators_detected?: Indicator[]
  patterns_detected?: Pattern[]
  trend?: string
  key_levels?: KeyLevels
  suggested_strategy?: SuggestedStrategy
  natural_language_summary?: string
  confidence?: number
  parse_failed?: boolean
  error?: string
  detail?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function TrendBadge({ trend }: { trend?: string }) {
  if (!trend) return null
  const lower = trend.toLowerCase()
  if (lower.includes('bull')) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-500/15 border border-green-500/30 text-green-400 text-xs font-medium">
        <TrendingUp size={12} /> Bullish
      </span>
    )
  }
  if (lower.includes('bear')) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-500/15 border border-red-500/30 text-red-400 text-xs font-medium">
        <TrendingDown size={12} /> Bearish
      </span>
    )
  }
  if (lower.includes('transit')) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-500/15 border border-blue-500/30 text-blue-400 text-xs font-medium">
        <RefreshCw size={12} /> Transitioning
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-yellow-500/15 border border-yellow-500/30 text-yellow-400 text-xs font-medium">
      <Minus size={12} /> Sideways
    </span>
  )
}

function ActionBadge({ action }: { action?: string }) {
  if (!action) return null
  const map: Record<string, string> = {
    BUY: 'bg-green-500/15 border-green-500/30 text-green-400',
    SELL: 'bg-red-500/15 border-red-500/30 text-red-400',
    WAIT: 'bg-yellow-500/15 border-yellow-500/30 text-yellow-400',
  }
  const cls = map[action.toUpperCase()] || 'bg-gray-700 border-gray-600 text-gray-300'
  return (
    <span className={`inline-flex items-center px-3 py-1 rounded-full border text-sm font-bold ${cls}`}>
      {action.toUpperCase()}
    </span>
  )
}

function ConfidenceMeter({ value }: { value?: number }) {
  if (value === undefined || value === null) return null
  const pct = Math.round(value * 100)
  const color = pct >= 70 ? '#00d97e' : pct >= 40 ? '#f59e0b' : '#ef4444'
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-gray-400">Confidence</span>
        <span className="text-xs font-mono font-semibold" style={{ color }}>
          {pct}%
        </span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export default function ChartVisionPage() {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dropZoneRef = useRef<HTMLDivElement>(null)

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [context, setContext] = useState('')
  const [analysis, setAnalysis] = useState<ChartAnalysis | null>(null)
  const [history, setHistory] = useState<ChartAnalysis[]>([])
  const [analyzing, setAnalyzing] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  // Load history on mount
  React.useEffect(() => {
    loadHistory()
  }, [])

  const loadHistory = async () => {
    try {
      setLoadingHistory(true)
      const items = await getChartVisionHistory()
      setHistory(items.slice(0, 5))
    } catch {
      // History is non-critical — silently ignore
    } finally {
      setLoadingHistory(false)
    }
  }

  const handleFileSelect = useCallback((file: File) => {
    if (!['image/png', 'image/jpeg', 'image/jpg', 'image/webp'].includes(file.type)) {
      setError('Only PNG, JPG, and WEBP images are accepted.')
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('Image is too large. Maximum size is 10 MB.')
      return
    }
    setError(null)
    setSelectedFile(file)
    setAnalysis(null)
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
  }, [])

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFileSelect(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFileSelect(file)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = () => setIsDragging(false)

  const handleAnalyze = async () => {
    if (!selectedFile) return
    try {
      setAnalyzing(true)
      setError(null)
      const result = await analyzeChart(selectedFile, context || undefined)
      setAnalysis(result)
      // Refresh history after new analysis
      await loadHistory()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed. Please try again.')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleHistorySelect = (item: ChartAnalysis) => {
    setAnalysis(item)
    setPreviewUrl(null)
    setSelectedFile(null)
  }

  const handleGenerateStrategy = () => {
    if (!analysis) return
    const params = new URLSearchParams()
    if (analysis.symbol) params.set('symbol', analysis.symbol)
    if (analysis.trend) params.set('trend', analysis.trend)
    if (analysis.suggested_strategy?.action) params.set('action', analysis.suggested_strategy.action)
    if (analysis.natural_language_summary)
      params.set('context', analysis.natural_language_summary.slice(0, 300))
    window.location.href = `/dashboard/strategy-builder?${params.toString()}`
  }

  return (
    <div className="min-h-screen bg-brand-dark p-4 md:p-6">
      <div className="max-w-7xl mx-auto">

        {/* ── Header ── */}
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 rounded-lg bg-cyan-500/15 border border-cyan-500/20">
            <Eye size={24} className="text-cyan-400" />
          </div>
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-gray-100">Chart Vision</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Upload a TradingView screenshot — AI identifies indicators, patterns, and strategy
            </p>
          </div>
        </div>

        {/* ── Global error banner ── */}
        {error && (
          <div className="mb-6 p-4 bg-red-900/20 border border-red-700/50 rounded-lg flex items-start gap-3 text-red-400">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <p className="text-sm">{error}</p>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">

          {/* ══════════════════════════════════════════════════════════ */}
          {/* Left: Upload + Results (3 cols on large screens)          */}
          {/* ══════════════════════════════════════════════════════════ */}
          <div className="lg:col-span-3 space-y-6">

            {/* ── Upload zone ── */}
            <div className="bg-brand-panel border border-gray-700 rounded-lg p-6">
              <h2 className="text-base font-semibold text-gray-100 mb-4 flex items-center gap-2">
                <Camera size={16} className="text-cyan-400" />
                Upload Chart Screenshot
              </h2>

              {/* Drop zone */}
              <div
                ref={dropZoneRef}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
                className={`relative cursor-pointer rounded-lg border-2 border-dashed transition-all duration-200 ${
                  isDragging
                    ? 'border-cyan-400 bg-cyan-500/10'
                    : 'border-gray-600 hover:border-cyan-500/50 hover:bg-gray-800/50'
                } ${previewUrl ? 'p-2' : 'p-10'}`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/jpg,image/webp"
                  className="hidden"
                  onChange={handleInputChange}
                />

                {previewUrl ? (
                  <div className="relative">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={previewUrl}
                      alt="Chart preview"
                      className="w-full max-h-80 object-contain rounded-lg"
                    />
                    <div className="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity bg-black/40 rounded-lg">
                      <span className="text-xs text-white font-medium">Click to change image</span>
                    </div>
                  </div>
                ) : (
                  <div className="text-center">
                    <Camera size={40} className="mx-auto mb-3 text-gray-600" />
                    <p className="text-sm font-medium text-gray-300">
                      Drag & drop a chart screenshot here
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      or click to browse — PNG, JPG, WEBP, max 10 MB
                    </p>
                  </div>
                )}
              </div>

              {/* Context field */}
              <div className="mt-4">
                <label className="block text-xs text-gray-400 mb-1">
                  Optional context (e.g. &ldquo;BTCUSD 1H with custom SMA44&rdquo;)
                </label>
                <input
                  type="text"
                  value={context}
                  onChange={(e) => setContext(e.target.value)}
                  placeholder="Add context to help the AI..."
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                />
              </div>

              {/* Analyze button */}
              <button
                onClick={handleAnalyze}
                disabled={!selectedFile || analyzing}
                className="mt-4 w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-2.5 bg-green-600 hover:bg-green-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-semibold rounded-lg transition-all duration-200 text-sm"
              >
                {analyzing ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <Sparkles size={16} />
                    Analyze Chart
                  </>
                )}
              </button>
            </div>

            {/* ── Results panel ── */}
            {analysis && (
              <div className="bg-brand-panel border border-cyan-500/20 rounded-lg overflow-hidden"
                style={{ boxShadow: '0 0 20px rgba(6,182,212,0.06)' }}
              >
                {/* Results header */}
                <div className="px-6 py-4 border-b border-gray-700 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-base font-semibold text-gray-100">Analysis Result</h2>
                    {analysis.symbol && analysis.symbol !== 'UNKNOWN' && (
                      <span className="px-2 py-0.5 rounded bg-gray-700 text-gray-200 text-xs font-mono font-bold">
                        {analysis.symbol}
                      </span>
                    )}
                    {analysis.timeframe && analysis.timeframe !== 'UNKNOWN' && (
                      <span className="px-2 py-0.5 rounded bg-gray-800 border border-gray-600 text-gray-400 text-xs font-mono">
                        {analysis.timeframe}
                      </span>
                    )}
                    <TrendBadge trend={analysis.trend} />
                  </div>
                  <button
                    onClick={handleGenerateStrategy}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600/80 hover:bg-purple-500 text-white text-xs font-medium rounded-lg transition-colors"
                  >
                    <Sparkles size={12} />
                    Generate Strategy
                    <ChevronRight size={12} />
                  </button>
                </div>

                <div className="p-6 space-y-6">

                  {/* Confidence meter */}
                  {analysis.confidence !== undefined && (
                    <ConfidenceMeter value={analysis.confidence} />
                  )}

                  {/* Summary */}
                  {analysis.natural_language_summary && (
                    <div className="p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                      <p className="text-sm text-gray-300 leading-relaxed">
                        {analysis.natural_language_summary}
                      </p>
                    </div>
                  )}

                  {/* Indicators + Patterns grid */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

                    {/* Indicators */}
                    {analysis.indicators_detected && analysis.indicators_detected.length > 0 && (
                      <div>
                        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
                          Indicators Detected ({analysis.indicators_detected.length})
                        </h3>
                        <div className="space-y-2">
                          {analysis.indicators_detected.map((ind, i) => (
                            <div
                              key={i}
                              className="flex items-center justify-between px-3 py-2 bg-gray-800 rounded-lg border border-gray-700"
                            >
                              <div className="flex items-center gap-2">
                                {ind.color && (
                                  <div
                                    className="w-3 h-3 rounded-full border border-gray-600 shrink-0"
                                    style={{ backgroundColor: ind.color }}
                                    title={ind.color}
                                  />
                                )}
                                <span className="text-sm text-gray-200 font-medium">
                                  {ind.name}
                                  {ind.period ? `(${ind.period})` : ''}
                                </span>
                              </div>
                              {ind.current_value && (
                                <span className="text-xs font-mono text-cyan-300">
                                  {ind.current_value}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Patterns */}
                    {analysis.patterns_detected && analysis.patterns_detected.length > 0 && (
                      <div>
                        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
                          Patterns Detected ({analysis.patterns_detected.length})
                        </h3>
                        <div className="space-y-2">
                          {analysis.patterns_detected.map((pat, i) => (
                            <div
                              key={i}
                              className="px-3 py-2 bg-gray-800 rounded-lg border border-gray-700"
                            >
                              <p className="text-sm font-medium text-purple-300">
                                {pat.pattern.replace(/_/g, ' ')}
                              </p>
                              {pat.description && (
                                <p className="text-xs text-gray-500 mt-0.5">{pat.description}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Key Levels */}
                  {analysis.key_levels &&
                    ((analysis.key_levels.support?.length ?? 0) > 0 ||
                      (analysis.key_levels.resistance?.length ?? 0) > 0) && (
                    <div>
                      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
                        Key Price Levels
                      </h3>
                      <div className="grid grid-cols-2 gap-3">
                        {(analysis.key_levels.support?.length ?? 0) > 0 && (
                          <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
                            <p className="text-xs font-semibold text-green-400 mb-2">Support</p>
                            {analysis.key_levels.support!.map((lvl, i) => (
                              <p key={i} className="text-sm font-mono text-green-300">
                                {typeof lvl === 'number' ? lvl.toLocaleString() : lvl}
                              </p>
                            ))}
                          </div>
                        )}
                        {(analysis.key_levels.resistance?.length ?? 0) > 0 && (
                          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                            <p className="text-xs font-semibold text-red-400 mb-2">Resistance</p>
                            {analysis.key_levels.resistance!.map((lvl, i) => (
                              <p key={i} className="text-sm font-mono text-red-300">
                                {typeof lvl === 'number' ? lvl.toLocaleString() : lvl}
                              </p>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Strategy Suggestion */}
                  {analysis.suggested_strategy && (
                    <div className="p-4 bg-gray-800/50 border border-gray-600 rounded-lg">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                          Strategy Suggestion
                        </h3>
                        <ActionBadge action={analysis.suggested_strategy.action} />
                      </div>

                      {analysis.suggested_strategy.reasoning && (
                        <p className="text-sm text-gray-300 mb-3">
                          {analysis.suggested_strategy.reasoning}
                        </p>
                      )}

                      <div className="space-y-2 text-sm">
                        {analysis.suggested_strategy.entry_condition && (
                          <div className="flex gap-2">
                            <span className="text-gray-500 shrink-0 w-24">Entry:</span>
                            <span className="text-gray-300">
                              {analysis.suggested_strategy.entry_condition}
                            </span>
                          </div>
                        )}
                        {analysis.suggested_strategy.stop_loss && (
                          <div className="flex gap-2">
                            <span className="text-red-400/70 shrink-0 w-24">Stop Loss:</span>
                            <span className="text-red-300">
                              {analysis.suggested_strategy.stop_loss}
                            </span>
                          </div>
                        )}
                        {analysis.suggested_strategy.take_profit && (
                          <div className="flex gap-2">
                            <span className="text-green-400/70 shrink-0 w-24">Take Profit:</span>
                            <span className="text-green-300">
                              {analysis.suggested_strategy.take_profit}
                            </span>
                          </div>
                        )}
                      </div>

                      {analysis.suggested_strategy.indicators_to_watch &&
                        analysis.suggested_strategy.indicators_to_watch.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-gray-700">
                          <p className="text-xs text-gray-500 mb-1">Watch:</p>
                          <div className="flex flex-wrap gap-1">
                            {analysis.suggested_strategy.indicators_to_watch.map((ind, i) => (
                              <span
                                key={i}
                                className="px-2 py-0.5 bg-gray-700 rounded text-xs text-gray-300"
                              >
                                {ind}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Parse failed fallback */}
                  {analysis.parse_failed && (
                    <div className="p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-xs text-yellow-300">
                      Note: The AI response could not be fully parsed as structured JSON.
                      The summary above is the raw output.
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* ══════════════════════════════════════════════════════════ */}
          {/* Right: History sidebar (1 col on large screens)           */}
          {/* ══════════════════════════════════════════════════════════ */}
          <div className="lg:col-span-1">
            <div className="bg-brand-panel border border-gray-700 rounded-lg p-4 sticky top-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                  <Clock size={14} className="text-gray-500" />
                  Recent Analyses
                </h2>
                <button
                  onClick={loadHistory}
                  disabled={loadingHistory}
                  className="text-gray-600 hover:text-gray-400 transition-colors"
                  title="Refresh history"
                >
                  <RefreshCw size={12} className={loadingHistory ? 'animate-spin' : ''} />
                </button>
              </div>

              {history.length === 0 && !loadingHistory && (
                <p className="text-xs text-gray-600 text-center py-6">
                  No analyses yet. Upload a chart to get started.
                </p>
              )}

              {loadingHistory && (
                <div className="flex justify-center py-6">
                  <Loader2 size={16} className="animate-spin text-gray-600" />
                </div>
              )}

              <div className="space-y-2">
                {history.map((item, i) => (
                  <button
                    key={i}
                    onClick={() => handleHistorySelect(item)}
                    className="w-full text-left p-3 bg-gray-800 hover:bg-gray-700 rounded-lg border border-gray-700 hover:border-cyan-500/30 transition-all duration-150 group"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-mono font-bold text-gray-200">
                        {item.symbol || 'UNKNOWN'}
                      </span>
                      {item.timeframe && item.timeframe !== 'UNKNOWN' && (
                        <span className="text-xs text-gray-500 font-mono">{item.timeframe}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <TrendBadge trend={item.trend} />
                    </div>
                    {item.suggested_strategy?.action && (
                      <p className="text-xs text-gray-500 mt-1">
                        Action:{' '}
                        <span
                          className={
                            item.suggested_strategy.action === 'BUY'
                              ? 'text-green-400'
                              : item.suggested_strategy.action === 'SELL'
                              ? 'text-red-400'
                              : 'text-yellow-400'
                          }
                        >
                          {item.suggested_strategy.action}
                        </span>
                      </p>
                    )}
                    <ChevronRight
                      size={12}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 group-hover:text-gray-400 hidden group-hover:block"
                    />
                  </button>
                ))}
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
