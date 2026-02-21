'use client'

import React, { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Brain, RefreshCw, BookOpen } from 'lucide-react'
import { ThoughtStream } from '@/components/brain/ThoughtStream'
import { MarketAnalysis } from '@/components/brain/MarketAnalysis'
import { StrategyScores } from '@/components/brain/StrategyScores'
import { NextMoves } from '@/components/brain/NextMoves'
import { LLMInsights } from '@/components/brain/LLMInsights'
import { PatternHeatmap } from '@/components/brain/PatternHeatmap'
import { LearningTips } from '@/components/brain/LearningTips'
import { StrategyScorecard } from '@/components/brain/StrategyScorecard'
import { useAppStore } from '@/store/useAppStore'

interface BrainState {
  thoughts: Array<{
    timestamp: string
    type: 'ANALYSIS' | 'DECISION' | 'LEARNING' | 'PLAN' | 'AI_INSIGHT'
    content: string
    confidence: number
    metadata: Record<string, any>
  }>
  market_analysis: {
    trend: string
    momentum: string
    volatility: string
    regime: string
    regime_confidence: number
    key_levels: { [key: string]: number }
    summary: string
  } | null
  next_moves: Array<{
    strategy: string
    action: string
    condition: string
    timeframe: string
    probability: number
  }>
  strategy_scores: Record<
    string,
    { confidence: number; reason: string; status: 'IDLE' | 'WATCHING' | 'WARMING_UP' | 'READY' | 'ACTIVE' }
  > | null
  last_updated: string
}

type LLMProvider = 'openai' | 'zai'

interface LLMProviderConfig {
  provider: LLMProvider
  configured: boolean
  default_model: string
  base_url: string
}

interface LLMRuntimeConfig {
  enabled: boolean
  provider: LLMProvider | 'none'
  model: string
  last_error?: string | null
  providers: LLMProviderConfig[]
  models: Record<string, string[]>
}

export default function BrainPage() {
  const router = useRouter()
  const [brainState, setBrainState] = useState<BrainState | null>(null)
  const [llmInsights, setLlmInsights] = useState<any[]>([])
  const [llmStats, setLlmStats] = useState<any>(null)
  const [llmConfig, setLlmConfig] = useState<LLMRuntimeConfig | null>(null)
  const [selectedProvider, setSelectedProvider] = useState<LLMProvider>('openai')
  const [selectedModel, setSelectedModel] = useState('')
  const [llmConfigDirty, setLlmConfigDirty] = useState(false)
  const [savingModelConfig, setSavingModelConfig] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastFetch, setLastFetch] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [isAuthRedirecting, setIsAuthRedirecting] = useState(false)

  // Learning patterns state
  const [hourPerf, setHourPerf] = useState<any>(null)
  const [dowPerf, setDowPerf] = useState<any>(null)
  const [strategyXP, setStrategyXP] = useState<Record<string, any>>({})
  const [rlStats, setRlStats] = useState<any>(null)
  const [showLearning, setShowLearning] = useState(false)

  const buildAuthHeaders = useCallback((token: string | null, withJson = false) => {
    const headers: Record<string, string> = token
      ? { Authorization: `Bearer ${token}`, Accept: 'application/json' }
      : { Accept: 'application/json' }
    if (withJson) {
      headers['Content-Type'] = 'application/json'
    }
    return headers
  }, [])

  const handleUnauthorized = useCallback(
    (message = 'Session expired. Please sign in again.') => {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('app-store')
      }
      try {
        useAppStore.getState().clearToken()
      } catch {
        // Best-effort logout cleanup
      }
      setError(message)

      if (!isAuthRedirecting) {
        setIsAuthRedirecting(true)
        router.replace('/login')
      }
    },
    [isAuthRedirecting, router],
  )

  const fetchBrainState = useCallback(async (isManual = false) => {
    try {
      if (isManual) setRefreshing(true)
      setError(null)

      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
      if (!token) {
        handleUnauthorized('Authentication token missing. Please sign in again.')
        return
      }
      const headers = buildAuthHeaders(token)

      const res = await fetch('/api/brain/state', { headers })

      if (res.status === 401) {
        handleUnauthorized()
        return
      }
      if (!res.ok) {
        throw new Error(`Brain API returned ${res.status}`)
      }

      const data = await res.json()
      setBrainState(data)
      setLastFetch(new Date())

      // Fetch optional LLM panels (non-blocking for base brain state)
      try {
        const [llmRes, llmConfigRes] = await Promise.all([
          fetch('/api/brain/llm-insights', { headers }),
          fetch('/api/brain/llm-config', { headers }),
        ])

        if (llmRes.status === 401 || llmConfigRes.status === 401) {
          handleUnauthorized()
          return
        }

        if (llmRes.ok) {
          const llmData = await llmRes.json()
          setLlmInsights(llmData.insights || [])
          setLlmStats(llmData.stats || null)
        }

        if (llmConfigRes.ok) {
          const configData: LLMRuntimeConfig = await llmConfigRes.json()
          setLlmConfig(configData)

          if (!llmConfigDirty) {
            const activeProvider: LLMProvider =
              configData.provider === 'zai' ? 'zai' : 'openai'
            const modelsForProvider = configData.models?.[activeProvider] || []

            setSelectedProvider(activeProvider)
            setSelectedModel(
              (activeProvider === configData.provider && configData.model)
                ? configData.model
                : (modelsForProvider[0] || ''),
            )
          }
        }
      } catch {
        // LLM insights are optional -- don't block on failure
      }

      // Fetch learning pattern data (non-blocking)
      try {
        const [hourRes, dowRes, xpRes, rlRes] = await Promise.allSettled([
          fetch('/api/brain/hour-performance', { headers }),
          fetch('/api/brain/dow-performance', { headers }),
          fetch('/api/brain/strategy-xp', { headers }),
          fetch('/api/brain/rl-stats', { headers }),
        ])

        if (hourRes.status === 'fulfilled' && hourRes.value.ok) {
          setHourPerf(await hourRes.value.json())
        }
        if (dowRes.status === 'fulfilled' && dowRes.value.ok) {
          setDowPerf(await dowRes.value.json())
        }
        if (xpRes.status === 'fulfilled' && xpRes.value.ok) {
          setStrategyXP(await xpRes.value.json())
        }
        if (rlRes.status === 'fulfilled' && rlRes.value.ok) {
          setRlStats(await rlRes.value.json())
        }
      } catch {
        // Learning pattern data is optional
      }
    } catch (err) {
      console.error('Error fetching brain state:', err)
      setError(err instanceof Error ? err.message : 'Failed to connect to Brain')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [buildAuthHeaders, handleUnauthorized, llmConfigDirty])

  useEffect(() => {
    fetchBrainState()
    const interval = setInterval(() => fetchBrainState(), 5000)
    return () => clearInterval(interval)
  }, [fetchBrainState])

  const thoughtCount = brainState?.thoughts?.length || 0
  const lastUpdated = brainState?.last_updated
    ? new Date(brainState.last_updated).toLocaleTimeString()
    : null
  const providerOptions: LLMProviderConfig[] = llmConfig?.providers || [
    { provider: 'openai', configured: false, default_model: 'gpt-4o-mini', base_url: '' },
    { provider: 'zai', configured: false, default_model: 'glm-4.6', base_url: '' },
  ]
  const selectedProviderConfig = llmConfig?.providers.find((p) => p.provider === selectedProvider) || null
  const modelsForSelectedProvider = llmConfig?.models?.[selectedProvider] || []

  const onProviderChange = (provider: LLMProvider) => {
    setSelectedProvider(provider)
    const providerModels = llmConfig?.models?.[provider] || []
    setSelectedModel(providerModels[0] || '')
    setLlmConfigDirty(true)
  }

  const onModelChange = (model: string) => {
    setSelectedModel(model)
    setLlmConfigDirty(true)
  }

  const saveLlmConfig = async () => {
    if (!selectedModel) {
      setError('Please select a model before applying.')
      return
    }

    try {
      setSavingModelConfig(true)
      setError(null)
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
      if (!token) {
        handleUnauthorized('Authentication token missing. Please sign in again.')
        return
      }

      const response = await fetch('/api/brain/llm-config', {
        method: 'PATCH',
        headers: buildAuthHeaders(token, true),
        body: JSON.stringify({
          provider: selectedProvider,
          model: selectedModel,
        }),
      })

      if (response.status === 401) {
        handleUnauthorized()
        return
      }
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || `Failed to apply model config (${response.status})`)
      }

      const updatedConfig: LLMRuntimeConfig = await response.json()
      setLlmConfig(updatedConfig)
      setLlmConfigDirty(false)
      setSelectedProvider(updatedConfig.provider === 'zai' ? 'zai' : 'openai')
      setSelectedModel(updatedConfig.model)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update LLM config')
    } finally {
      setSavingModelConfig(false)
    }
  }

  return (
    <div className="min-h-screen bg-brand-dark p-4 md:p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-purple-500/15 border border-purple-500/20">
              <Brain size={24} className="text-purple-400" />
            </div>
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-gray-100">Brain</h1>
              <p className="text-gray-400 text-sm mt-0.5">
                {lastFetch ? `Synced ${lastFetch.toLocaleTimeString()}` : 'Connecting...'}
                <span className="ml-2 text-gray-600">&bull;</span>
                <span className="ml-2">Auto-refresh 5s</span>
              </p>
            </div>
          </div>
          <button
            onClick={() => fetchBrainState(true)}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2 bg-purple-500/15 text-purple-300 border border-purple-500/20 rounded-lg font-medium text-sm hover:bg-purple-500/25 transition-all duration-200 disabled:opacity-50"
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Syncing...' : 'Refresh'}
          </button>
        </div>

        {/* Error State */}
        {error && (
          <div className="mb-6 p-4 bg-red-900/20 border border-red-700/50 rounded-lg text-red-400">
            <p className="text-sm">{error}</p>
            <button
              onClick={() => fetchBrainState(true)}
              className="mt-2 text-xs text-red-300 hover:text-red-200 underline"
            >
              Try again
            </button>
          </div>
        )}

        {/* Top Section: Market Analysis */}
        <div className="mb-6">
          <MarketAnalysis data={brainState?.market_analysis || null} loading={loading} />
        </div>

        {/* Middle Section: Two Columns */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 mb-6">
          {/* Left Column (60%): Thought Stream */}
          <div className="lg:col-span-3">
            <div className="bg-brand-panel border border-gray-700 rounded-lg overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-gray-100">Thought Stream</h3>
                <span className="text-xs text-gray-500 font-mono">{thoughtCount} thoughts</span>
              </div>
              <div className="px-6 py-4">
                <ThoughtStream
                  thoughts={brainState?.thoughts || []}
                  loading={loading}
                />
              </div>
            </div>
          </div>

          {/* Right Column (40%): Strategy Scores + Next Moves */}
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-brand-panel border border-gray-700 rounded-lg p-4">
              <StrategyScores
                scores={brainState?.strategy_scores || null}
                loading={loading}
              />
            </div>
            <div className="bg-brand-panel border border-gray-700 rounded-lg p-4">
              <NextMoves
                moves={brainState?.next_moves || null}
                loading={loading}
              />
            </div>
          </div>
        </div>

        {/* AI Insights Section */}
        <div className="mb-6">
          <div className="bg-brand-panel border border-indigo-500/20 rounded-lg overflow-hidden"
            style={{ boxShadow: '0 0 20px rgba(99, 102, 241, 0.06)' }}
          >
            <div className="px-6 pt-5 pb-4 border-b border-indigo-500/10">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <h4 className="text-sm font-semibold text-indigo-200">Brain LLM Model</h4>
                  <p className="text-xs text-gray-400 mt-1">
                    Select provider + model for AI analysis used by the engine.
                  </p>
                </div>

                <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
                  <select
                    value={selectedProvider}
                    onChange={(e) => onProviderChange(e.target.value as LLMProvider)}
                    className="px-3 py-2 rounded-md bg-gray-900 border border-gray-700 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    aria-label="Select LLM provider"
                  >
                    {providerOptions.map((provider) => (
                      <option key={provider.provider} value={provider.provider}>
                        {provider.provider.toUpperCase()} {provider.configured ? '' : '(no key)'}
                      </option>
                    ))}
                  </select>

                  <select
                    value={selectedModel}
                    onChange={(e) => onModelChange(e.target.value)}
                    className="px-3 py-2 rounded-md bg-gray-900 border border-gray-700 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    aria-label="Select LLM model"
                    disabled={!selectedProviderConfig?.configured || modelsForSelectedProvider.length === 0}
                  >
                    {modelsForSelectedProvider.map((model) => (
                      <option key={model} value={model}>{model}</option>
                    ))}
                  </select>

                  <button
                    onClick={saveLlmConfig}
                    disabled={
                      savingModelConfig
                      || !llmConfigDirty
                      || !selectedModel
                      || !selectedProviderConfig?.configured
                    }
                    className="px-3 py-2 rounded-md text-sm font-medium bg-indigo-600/80 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {savingModelConfig ? 'Applying...' : 'Apply Model'}
                  </button>
                </div>
              </div>

              {llmConfig && !selectedProviderConfig?.configured && (
                <p className="mt-2 text-xs text-amber-300">
                  {selectedProvider.toUpperCase()} API key is missing in environment.
                </p>
              )}
              {llmConfig?.last_error && (
                <p className="mt-2 text-xs text-red-300">{llmConfig.last_error}</p>
              )}
            </div>
            <div className="px-6 py-4">
              <LLMInsights
                insights={llmInsights}
                stats={llmStats}
                loading={loading}
              />
            </div>
          </div>
        </div>

        {/* ─── Learning Patterns Section ─── */}
        <div className="mb-6">
          {/* Section toggle header */}
          <button
            onClick={() => setShowLearning((v) => !v)}
            className="w-full flex items-center justify-between px-5 py-3 bg-brand-panel border border-[#00d97e]/20 rounded-lg hover:border-[#00d97e]/40 transition-all duration-200 group"
            style={{ boxShadow: '0 0 12px rgba(0,217,126,0.04)' }}
          >
            <div className="flex items-center gap-3">
              <div className="p-1.5 rounded-md bg-[#00d97e]/10 border border-[#00d97e]/20">
                <BookOpen size={16} className="text-[#00d97e]" />
              </div>
              <div className="text-left">
                <h3 className="text-sm font-semibold text-gray-100">Learning Patterns</h3>
                <p className="text-xs text-gray-500">
                  Strategy heatmaps, scorecards & brain insights
                </p>
              </div>
            </div>
            <span className="text-gray-500 group-hover:text-gray-300 transition-colors text-xs font-mono">
              {showLearning ? '▲ hide' : '▼ show'}
            </span>
          </button>

          {showLearning && (
            <div className="mt-4 space-y-6">
              {/* Learning Tips */}
              {llmInsights.length > 0 && (
                <LearningTips
                  insights={llmInsights
                    .filter((i: any) => !i.is_error && i.content)
                    .map((i: any) => i.content as string)
                    .slice(0, 20)}
                />
              )}
              {llmInsights.length === 0 && <LearningTips insights={[]} />}

              {/* Heatmaps */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {/* Hour performance heatmap */}
                <div className="bg-brand-panel border border-gray-700 rounded-lg p-5">
                  <PatternHeatmap
                    title="Strategy x Hour of Day"
                    data={hourPerf?.data ?? {}}
                    rowLabels={hourPerf?.row_labels ?? []}
                    colLabels={hourPerf?.col_labels ?? []}
                  />
                  {!hourPerf && (
                    <p className="text-xs text-gray-600 mt-2">
                      Waiting for hour performance data…
                    </p>
                  )}
                </div>

                {/* Day-of-week performance heatmap */}
                <div className="bg-brand-panel border border-gray-700 rounded-lg p-5">
                  <PatternHeatmap
                    title="Strategy x Day of Week"
                    data={dowPerf?.data ?? {}}
                    rowLabels={dowPerf?.row_labels ?? []}
                    colLabels={dowPerf?.col_labels ?? []}
                  />
                  {!dowPerf && (
                    <p className="text-xs text-gray-600 mt-2">
                      Waiting for day-of-week performance data…
                    </p>
                  )}
                </div>
              </div>

              {/* Strategy Scorecards */}
              {Object.keys(strategyXP).length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
                    Strategy Scorecards
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                    {(() => {
                      const entries = Object.entries(strategyXP) as [string, any][]
                      // Find top strategy by win_rate
                      const topCode = entries.reduce(
                        (best, [code, xp]) =>
                          (xp.win_rate ?? 0) > (strategyXP[best]?.win_rate ?? 0)
                            ? code
                            : best,
                        entries[0]?.[0] ?? '',
                      )
                      return entries.map(([code, xp]) => (
                        <StrategyScorecard
                          key={code}
                          strategyCode={code}
                          strategyName={xp.name ?? `Strategy ${code}`}
                          xpData={{
                            level: xp.level ?? 1,
                            xp: xp.total_xp ?? 0,
                            xp_to_next: xp.xp_to_next_level ?? 100,
                            win_rate: xp.win_rate ?? 0,
                            total_trades: xp.total_trades ?? 0,
                            total_profit: 0,
                            current_streak: xp.current_streak ?? 0,
                            current_streak_type: xp.current_streak_type ?? 'win',
                          }}
                          allocation={
                            rlStats?.allocations?.[code] ??
                            rlStats?.strategy_allocations?.[code] ??
                            0
                          }
                          fitnessScore={
                            rlStats?.fitness_scores?.[code] ??
                            rlStats?.strategy_scores?.[code]?.fitness ??
                            0
                          }
                          rlExpectedValue={
                            rlStats?.expected_values?.[code] ??
                            rlStats?.strategy_scores?.[code]?.ev ??
                            0
                          }
                          isTop={code === topCode}
                        />
                      ))
                    })()}
                  </div>
                </div>
              )}

              {Object.keys(strategyXP).length === 0 && (
                <div className="bg-brand-panel border border-gray-800 rounded-lg p-6 text-center">
                  <p className="text-sm text-gray-500">
                    No strategy XP data yet — scorecards will appear once strategies start trading.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Bottom Section: Brain Activity Indicator */}
        <div className="bg-brand-panel border border-gray-700 rounded-lg px-6 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {/* Animated pulse line */}
              <div className="flex items-center gap-1">
                {Array.from({ length: 12 }).map((_, i) => (
                  <div
                    key={i}
                    className="w-1 bg-purple-500/60 rounded-full"
                    style={{
                      height: `${8 + Math.sin((i / 12) * Math.PI * 2) * 6}px`,
                      animation: 'pulse 2s ease-in-out infinite',
                      animationDelay: `${i * 100}ms`,
                    }}
                  />
                ))}
              </div>
              <span className="text-xs text-gray-400">
                Brain {brainState ? 'active' : 'connecting...'}
              </span>
            </div>

            <div className="flex items-center gap-4 text-xs text-gray-500">
              <span>
                {thoughtCount} thought{thoughtCount !== 1 ? 's' : ''} recorded
              </span>
              {lastUpdated && (
                <>
                  <span className="text-gray-700">&bull;</span>
                  <span>Last update: {lastUpdated}</span>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Global animation styles */}
      <style jsx global>{`
        @keyframes fade-in {
          from {
            opacity: 0;
            transform: translateY(-8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-fade-in {
          animation: fade-in 0.4s ease-out;
        }
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
      `}</style>
    </div>
  )
}
