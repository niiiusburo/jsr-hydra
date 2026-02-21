'use client'

import React, { useEffect, useRef } from 'react'

interface ThoughtMetadata {
  symbol?: string
  price?: number
  price_change?: number
  price_change_pct?: number
  bid?: number
  ask?: number
  trigger?: string
  llm_error?: boolean
  [key: string]: any
}

interface Thought {
  timestamp: string
  type: 'ANALYSIS' | 'DECISION' | 'LEARNING' | 'PLAN' | 'AI_INSIGHT'
  content: string
  confidence: number
  metadata: ThoughtMetadata
}

interface ThoughtStreamProps {
  thoughts: Thought[]
  loading?: boolean
}

const typeConfig: Record<string, { icon: string; color: string; bg: string; glow?: string }> = {
  ANALYSIS: { icon: '\u{1F9E0}', color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20' },
  DECISION: { icon: '\u26A1', color: 'text-yellow-400', bg: 'bg-yellow-500/10 border-yellow-500/20' },
  LEARNING: { icon: '\u{1F4DA}', color: 'text-green-400', bg: 'bg-green-500/10 border-green-500/20' },
  PLAN: { icon: '\u{1F3AF}', color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/20' },
  AI_INSIGHT: { icon: '\u2728', color: 'text-indigo-300', bg: 'bg-gradient-to-r from-indigo-950/40 via-purple-950/20 to-transparent border-indigo-500/30', glow: '0 0 12px rgba(99, 102, 241, 0.15), 0 0 24px rgba(139, 92, 246, 0.08)' },
}

function getRelativeTime(timestamp: string): string {
  const now = new Date()
  const then = new Date(timestamp)
  const diffMs = now.getTime() - then.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)

  if (diffSeconds < 10) return 'just now'
  if (diffSeconds < 60) return `${diffSeconds}s ago`

  const diffMinutes = Math.floor(diffSeconds / 60)
  if (diffMinutes < 60) return `${diffMinutes}m ago`

  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`

  return `${Math.floor(diffHours / 24)}d ago`
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function formatPrice(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1000) return value.toFixed(2)
  if (abs >= 100) return value.toFixed(3)
  if (abs >= 1) return value.toFixed(5)
  return value.toFixed(6)
}

function formatSignedValue(value: number, decimals: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '' : ''
  return `${sign}${value.toFixed(decimals)}`
}

function formatSignedPercent(value: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '' : ''
  return `${sign}${value.toFixed(3)}%`
}

function priceDeltaDecimals(price: number): number {
  const abs = Math.abs(price)
  if (abs >= 1000) return 2
  if (abs >= 100) return 3
  if (abs >= 1) return 5
  return 6
}

function getPriceContext(metadata: ThoughtMetadata) {
  const symbol = typeof metadata?.symbol === 'string' ? metadata.symbol : null
  const explicitPrice = toFiniteNumber(metadata?.price)
  const bid = toFiniteNumber(metadata?.bid)
  const ask = toFiniteNumber(metadata?.ask)

  const price =
    explicitPrice ??
    (bid !== null && ask !== null ? (bid + ask) / 2 : bid ?? ask)

  const change = toFiniteNumber(metadata?.price_change)
  const changePct = toFiniteNumber(metadata?.price_change_pct)

  return {
    symbol,
    price,
    change,
    changePct,
  }
}

export function ThoughtStream({ thoughts, loading = false }: ThoughtStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const prevCountRef = useRef(thoughts.length)

  useEffect(() => {
    if (thoughts.length > prevCountRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = 0
    }
    prevCountRef.current = thoughts.length
  }, [thoughts.length])

  if (loading && thoughts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-400">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 bg-purple-500 rounded-full animate-pulse" />
          <div className="w-2 h-2 bg-purple-500 rounded-full animate-pulse" style={{ animationDelay: '150ms' }} />
          <div className="w-2 h-2 bg-purple-500 rounded-full animate-pulse" style={{ animationDelay: '300ms' }} />
        </div>
        <span className="text-sm">Brain is thinking...</span>
      </div>
    )
  }

  if (thoughts.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500 text-sm">
        No thoughts yet. Brain is warming up...
      </div>
    )
  }

  return (
    <div
      ref={scrollRef}
      className="space-y-3 max-h-[500px] overflow-y-auto pr-2 scrollbar-thin"
      style={{ scrollBehavior: 'smooth' }}
    >
      {thoughts.map((thought, index) => {
        const config = typeConfig[thought.type] || typeConfig.ANALYSIS
        const isNew = index === 0
        const priceCtx = getPriceContext(thought.metadata || {})
        const hasPrice = priceCtx.price !== null
        const hasChange = priceCtx.change !== null
        const trigger =
          typeof thought.metadata?.trigger === 'string' ? thought.metadata.trigger : null
        const llmError = thought.metadata?.llm_error === true
        const moveColor =
          priceCtx.change !== null && priceCtx.change > 0
            ? 'text-green-300'
            : priceCtx.change !== null && priceCtx.change < 0
            ? 'text-red-300'
            : 'text-gray-400'
        const moveMarker =
          priceCtx.change !== null && priceCtx.change > 0
            ? '▲'
            : priceCtx.change !== null && priceCtx.change < 0
            ? '▼'
            : '•'

        return (
          <div
            key={`${thought.timestamp}-${index}`}
            className={`relative border rounded-lg p-3 transition-all duration-500 ${config.bg} ${
              isNew ? 'animate-fade-in' : ''
            }`}
            style={config.glow ? { boxShadow: config.glow } : undefined}
          >
            {/* Type icon + timestamp row */}
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <span className="text-base">{config.icon}</span>
                <span className={`text-xs font-semibold uppercase tracking-wide ${config.color}`}>
                  {thought.type}
                </span>
              </div>
              <span className="text-xs text-gray-500 font-mono">
                {getRelativeTime(thought.timestamp)}
              </span>
            </div>

            {/* Content */}
            {hasPrice && (
              <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11px]">
                {priceCtx.symbol && (
                  <span className="px-1.5 py-0.5 rounded bg-gray-900/70 border border-gray-700 text-gray-300 font-mono">
                    {priceCtx.symbol}
                  </span>
                )}
                <span className="text-gray-300 font-mono">
                  Price {formatPrice(priceCtx.price as number)}
                </span>
                {hasChange && (
                  <span className={`font-mono ${moveColor}`}>
                    {moveMarker}{' '}
                    {formatSignedValue(
                      priceCtx.change as number,
                      priceDeltaDecimals(priceCtx.price as number),
                    )}
                    {priceCtx.changePct !== null
                      ? ` (${formatSignedPercent(priceCtx.changePct)})`
                      : ''}
                  </span>
                )}
              </div>
            )}
            {(trigger || llmError) && (
              <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[10px]">
                {trigger && (
                  <span className="px-1.5 py-0.5 rounded border border-gray-600 bg-gray-900/40 text-gray-300 uppercase tracking-wide">
                    {trigger.replace(/_/g, ' ')}
                  </span>
                )}
                {llmError && (
                  <span className="px-1.5 py-0.5 rounded border border-red-500/50 bg-red-900/20 text-red-300 uppercase tracking-wide">
                    LLM Error
                  </span>
                )}
              </div>
            )}
            <p className="text-sm text-gray-200 leading-relaxed">{thought.content}</p>

            {/* Confidence bar */}
            <div className="mt-2 flex items-center gap-2">
              <span className="text-xs text-gray-500">Confidence</span>
              <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${
                    thought.confidence >= 0.7
                      ? 'bg-green-500'
                      : thought.confidence >= 0.4
                      ? 'bg-yellow-500'
                      : 'bg-red-500'
                  }`}
                  style={{ width: `${thought.confidence * 100}%` }}
                />
              </div>
              <span className="text-xs text-gray-400 font-mono w-10 text-right">
                {(thought.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
