'use client'

import React from 'react'
import { BarChart3, ArrowRightLeft, Settings, TrendingUp, Cpu, Zap } from 'lucide-react'

interface LLMInsight {
  type: 'market_analysis' | 'trade_review' | 'strategy_review' | 'regime_analysis' | 'loss_diagnosis'
  timestamp: string
  content: string
  model?: string
  provider?: string
  is_error?: boolean
  error_message?: string
  tokens_used?: number
  trade_symbol?: string
  trade_pnl?: number
  old_regime?: string
  new_regime?: string
}

interface LLMStats {
  provider?: string
  total_calls: number
  total_tokens_used: number
  estimated_cost_usd: number
  model: string
  insights_count: number
  last_error?: string
  message?: string
}

interface LLMInsightsProps {
  insights: LLMInsight[]
  stats: LLMStats | null
  loading?: boolean
}

const typeConfig: Record<
  string,
  { icon: React.ReactNode; label: string; color: string; borderColor: string }
> = {
  market_analysis: {
    icon: <BarChart3 size={14} />,
    label: 'Market Analysis',
    color: 'text-indigo-300',
    borderColor: 'border-indigo-500/30',
  },
  trade_review: {
    icon: <TrendingUp size={14} />,
    label: 'Trade Review',
    color: 'text-cyan-300',
    borderColor: 'border-cyan-500/30',
  },
  strategy_review: {
    icon: <Settings size={14} />,
    label: 'Strategy Review',
    color: 'text-violet-300',
    borderColor: 'border-violet-500/30',
  },
  regime_analysis: {
    icon: <ArrowRightLeft size={14} />,
    label: 'Regime Analysis',
    color: 'text-fuchsia-300',
    borderColor: 'border-fuchsia-500/30',
  },
  loss_diagnosis: {
    icon: <Zap size={14} />,
    label: 'Loss Diagnosis',
    color: 'text-amber-300',
    borderColor: 'border-amber-500/30',
  },
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

function normalizeInsightError(insight: LLMInsight): string {
  const raw = (insight.error_message || insight.content || '').trim()
  if (raw.length === 0) return 'Unknown LLM runtime error.'
  return raw
}

function isInsightError(insight: LLMInsight): boolean {
  if (insight.is_error) return true
  return (insight.content || '').trim().startsWith('[LLM Error')
}

export function LLMInsights({ insights, stats, loading = false }: LLMInsightsProps) {
  if (loading && insights.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-gray-400">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
          <div
            className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse"
            style={{ animationDelay: '150ms' }}
          />
          <div
            className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse"
            style={{ animationDelay: '300ms' }}
          />
        </div>
        <span className="text-sm">Loading AI insights...</span>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-indigo-500/15 border border-indigo-500/20">
            <Cpu size={16} className="text-indigo-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-100">AI Insights</h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/20">
            {(stats?.provider || 'llm').toUpperCase()}
          </span>
        </div>
        {stats && stats.total_calls > 0 && (
          <span className="text-xs text-gray-500 font-mono">
            {stats.insights_count} insight{stats.insights_count !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Insights List */}
      {insights.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-32 text-gray-500 text-sm">
          <Zap size={20} className="text-gray-600 mb-2" />
          {stats?.message ? (
            <span>{stats.message}</span>
          ) : (
            <span>No AI insights yet. First analysis in ~15 minutes.</span>
          )}
        </div>
      ) : (
        <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2 scrollbar-thin">
          {insights.map((insight, index) => {
            const isError = isInsightError(insight)
            const baseConfig = typeConfig[insight.type] || typeConfig.market_analysis
            const config = isError
              ? {
                  ...baseConfig,
                  color: 'text-red-300',
                  borderColor: 'border-red-500/40',
                }
              : baseConfig
            const isNew = index === 0

            return (
              <div
                key={`${insight.timestamp}-${index}`}
                className={`relative rounded-lg p-3 transition-all duration-500 border ${config.borderColor} bg-gradient-to-r from-indigo-950/40 via-purple-950/20 to-transparent ${
                  isNew ? 'animate-fade-in' : ''
                }`}
                style={{
                  boxShadow: isNew
                    ? '0 0 15px rgba(99, 102, 241, 0.15), 0 0 30px rgba(139, 92, 246, 0.08)'
                    : '0 0 8px rgba(99, 102, 241, 0.06)',
                }}
              >
                {/* Type badge + timestamp */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className={config.color}>{config.icon}</span>
                    <span
                      className={`text-xs font-semibold uppercase tracking-wide ${config.color}`}
                    >
                      {config.label}
                    </span>
                    {isError && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded border border-red-500/40 text-red-300 font-semibold tracking-wide">
                        LLM ERROR
                      </span>
                    )}
                    {insight.trade_symbol && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-gray-700/60 text-gray-300 font-mono">
                        {insight.trade_symbol}
                      </span>
                    )}
                    {insight.trade_pnl !== undefined && insight.trade_pnl !== null && (
                      <span
                        className={`text-xs font-mono ${
                          insight.trade_pnl > 0 ? 'text-green-400' : 'text-red-400'
                        }`}
                      >
                        {insight.trade_pnl > 0 ? '+' : ''}${insight.trade_pnl.toFixed(2)}
                      </span>
                    )}
                    {insight.old_regime && insight.new_regime && (
                      <span className="text-xs text-gray-400">
                        {insight.old_regime} &rarr; {insight.new_regime}
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-gray-500 font-mono">
                    {getRelativeTime(insight.timestamp)}
                  </span>
                </div>

                {/* Content */}
                <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-line">
                  {isError ? normalizeInsightError(insight) : insight.content}
                </p>
              </div>
            )
          })}
        </div>
      )}

      {/* Stats Footer */}
      {stats && stats.total_calls > 0 && (
        <div className="mt-4 pt-3 border-t border-gray-700/50">
          {stats.last_error && (
            <div className="mb-2 text-xs text-red-300">
              Last LLM error: <span className="text-red-200">{stats.last_error}</span>
            </div>
          )}
          <div className="flex items-center justify-between text-xs text-gray-500">
            <div className="flex items-center gap-4">
              {stats.provider && stats.provider !== 'none' && (
                <span>
                  Provider: <span className="text-gray-400 font-mono">{stats.provider}</span>
                </span>
              )}
              <span>
                Model: <span className="text-gray-400 font-mono">{stats.model}</span>
              </span>
              <span>
                Calls: <span className="text-gray-400 font-mono">{stats.total_calls}</span>
              </span>
              <span>
                Tokens:{' '}
                <span className="text-gray-400 font-mono">
                  {stats.total_tokens_used.toLocaleString()}
                </span>
              </span>
            </div>
            <span>
              Cost:{' '}
              <span className="text-indigo-400 font-mono">
                ${stats.estimated_cost_usd.toFixed(4)}
              </span>
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
