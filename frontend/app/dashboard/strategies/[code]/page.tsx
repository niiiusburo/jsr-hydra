'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Card } from '@/components/ui/Card'
import { StrategyXPBar } from '@/components/strategies/StrategyXPBar'
import { StrategyBadges } from '@/components/strategies/StrategyBadges'

// ────────────────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────────────────

interface StrategyInfo {
  code: string
  name: string
  status: string
  allocation_pct: number
  win_rate: number
  profit_factor: number
  total_trades: number
  total_profit: number
  config?: Record<string, any>
}

interface XPData {
  code: string
  name: string
  total_xp: number
  level: number
  level_name: string
  level_color: string
  xp_to_next_level: number
  xp_current_level: number
  xp_needed_for_level: number
  progress_pct: number
  total_trades: number
  wins: number
  losses: number
  win_rate: number
  best_streak: number
  current_streak: number
  current_streak_type: string
  worst_streak: number
  skills_unlocked: string[]
  badges: any[]
  total_profit: number
  best_trade: number
  worst_trade: number
  avg_duration_seconds: number
  xp_history: any[]
}

interface Trade {
  ticket: number
  strategy: string
  symbol: string
  direction: string
  entry_price: number
  exit_price: number
  profit: number
  lots: number
  opened_at: string
  closed_at: string
  duration_seconds: number
}

// ────────────────────────────────────────────────────────────────
// Strategy Descriptions
// ────────────────────────────────────────────────────────────────

const STRATEGY_DESCRIPTIONS: Record<string, { title: string; description: string; parameters: Record<string, string> }> = {
  A: {
    title: 'Trend Following',
    description:
      'Trend Following uses EMA 9/21 crossovers and pullbacks. When the fast EMA crosses above the slow EMA, it signals an uptrend. The strategy also enters on pullbacks to the fast EMA during established trends. ADX must be above 15 to confirm trend strength.',
    parameters: {
      'Fast EMA': '9',
      'Slow EMA': '21',
      'ADX Threshold': '15',
      'Entry': 'EMA crossover + pullback',
      'Exit': 'Opposite crossover or trailing stop',
      'Risk per trade': '1% of equity',
    },
  },
  B: {
    title: 'Mean Reversion',
    description:
      'Mean Reversion trades when price deviates significantly from its average (Z-score > 1.3). It buys when price drops below the lower Bollinger Band and sells when it rises above the upper band, expecting price to return to the mean.',
    parameters: {
      'BB Period': '20',
      'BB StdDev': '2.0',
      'Z-Score Threshold': '1.3',
      'Entry': 'Price outside Bollinger Bands',
      'Exit': 'Return to middle band or opposite band',
      'Risk per trade': '0.75% of equity',
    },
  },
  C: {
    title: 'Session Breakout',
    description:
      'Session Breakout identifies price compression during quiet periods and trades the breakout. When price breaks above or below the recent 12-bar range by 0.5x ATR, it enters in the breakout direction.',
    parameters: {
      'Range Bars': '12',
      'ATR Multiplier': '0.5x (entry), 1.5x (TP)',
      'SL Distance': '1.0x ATR',
      'Entry': 'Range breakout + ATR filter',
      'Exit': 'Target hit or range re-entry',
      'Risk per trade': '1% of equity',
    },
  },
  D: {
    title: 'Momentum Scalper',
    description:
      'Momentum Scalper detects short-term momentum bursts using RSI extremes and Bollinger Band touches. It enters quickly on momentum signals and exits with tight 1.0 ATR stops and 1.5 ATR targets.',
    parameters: {
      'RSI Period': '14',
      'RSI Oversold': '30',
      'RSI Overbought': '70',
      'SL Distance': '1.0x ATR',
      'TP Distance': '1.5x ATR',
      'Entry': 'RSI extreme + BB touch',
      'Exit': 'TP/SL hit or RSI reversal',
      'Risk per trade': '0.5% of equity',
    },
  },
  E: {
    title: 'Range Scalper (Sideways)',
    description:
      'Range Scalper is designed for sideways markets. It only fires when ADX is low, then fades extremes at the Bollinger Bands with RSI confirmation. Entries are quick, stops are tight (0.8 ATR), and targets aim for mean reversion toward the middle band.',
    parameters: {
      'Timeframe': 'M5',
      'ADX Filter': '<= 20 (sideways only)',
      'BB Period': '20',
      'RSI Period': '9',
      'RSI Buy/Sell': '<= 35 / >= 65',
      'SL Distance': '0.8x ATR',
      'TP Distance': 'Middle BB (min 0.6x ATR)',
      'Risk per trade': '0.5% of equity',
    },
  },
}

// ────────────────────────────────────────────────────────────────
// Helper: Auth headers
// ────────────────────────────────────────────────────────────────

function getHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

// ────────────────────────────────────────────────────────────────
// Component
// ────────────────────────────────────────────────────────────────

export default function StrategyDetailPage() {
  const params = useParams()
  const router = useRouter()
  const code = (params.code as string || '').toUpperCase()

  const [strategy, setStrategy] = useState<StrategyInfo | null>(null)
  const [xpData, setXpData] = useState<XPData | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [rlStats, setRlStats] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const strategyDesc = STRATEGY_DESCRIPTIONS[code]

  useEffect(() => {
    if (!code || !['A', 'B', 'C', 'D', 'E'].includes(code)) {
      setError('Invalid strategy code')
      setIsLoading(false)
      return
    }

    const fetchAll = async () => {
      try {
        setIsLoading(true)
        setError(null)
        const headers = getHeaders()

        const [stratRes, xpRes, tradesRes, rlRes] = await Promise.allSettled([
          fetch(`/api/strategies/${code}`, { headers }),
          fetch('/api/brain/strategy-xp', { headers }),
          fetch(`/api/trades?strategy_filter=${code}&per_page=20`, { headers }),
          fetch('/api/brain/rl-stats', { headers }),
        ])

        // Strategy info
        if (stratRes.status === 'fulfilled' && stratRes.value.ok) {
          const data = await stratRes.value.json()
          setStrategy({
            ...data,
            status: (data.status || '').toLowerCase(),
          })
        }

        // XP data
        if (xpRes.status === 'fulfilled' && xpRes.value.ok) {
          const data = await xpRes.value.json()
          if (data[code]) {
            setXpData(data[code])
          }
        }

        // Trades
        if (tradesRes.status === 'fulfilled' && tradesRes.value.ok) {
          const data = await tradesRes.value.json()
          setTrades(Array.isArray(data) ? data : data.trades || [])
        }

        // RL Stats
        if (rlRes.status === 'fulfilled' && rlRes.value.ok) {
          setRlStats(await rlRes.value.json())
        }
      } catch (err) {
        console.error('Error fetching strategy detail:', err)
        setError(err instanceof Error ? err.message : 'Failed to load strategy')
      } finally {
        setIsLoading(false)
      }
    }

    fetchAll()
    const interval = setInterval(fetchAll, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [code])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-gray-400">Loading strategy details...</div>
      </div>
    )
  }

  if (error || !strategyDesc) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-4">
        <div className="text-red-400">{error || 'Strategy not found'}</div>
        <button
          onClick={() => router.push('/dashboard/strategies')}
          className="text-sm text-blue-400 hover:text-blue-300 underline"
        >
          Back to Strategies
        </button>
      </div>
    )
  }

  // Duration formatting helper
  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${Math.round(seconds)}s`
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`
    return `${(seconds / 3600).toFixed(1)}h`
  }

  // Extract RL distributions for this strategy
  const rlDistributions = rlStats?.distributions
    ? Object.entries(rlStats.distributions)
        .filter(([key]) => key.startsWith(`${code}_`))
        .map(([key, value]) => ({
          regime: key.replace(`${code}_`, ''),
          ...(value as any),
        }))
    : []

  return (
    <div className="space-y-6">
      {/* Back button + header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => router.push('/dashboard/strategies')}
          className="text-gray-400 hover:text-gray-200 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 className="text-3xl font-bold text-gray-100">
            Strategy {code}: {strategyDesc.title}
          </h1>
          <p className="text-gray-400 mt-1">
            {strategy?.status === 'active' && <span className="text-green-400 mr-2">Active</span>}
            {strategy?.status === 'paused' && <span className="text-yellow-400 mr-2">Paused</span>}
            {strategy?.status === 'stopped' && <span className="text-red-400 mr-2">Stopped</span>}
            {strategy ? `${strategy.allocation_pct}% allocation` : ''}
          </p>
        </div>
      </div>

      {/* 1. XP Bar (Hero) */}
      {xpData && (
        <Card className="p-6">
          <StrategyXPBar data={xpData} />
        </Card>
      )}

      {/* 2. Algorithm Explanation */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold text-gray-100 mb-3">Algorithm</h2>
        <p className="text-gray-300 text-sm leading-relaxed mb-4">{strategyDesc.description}</p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {Object.entries(strategyDesc.parameters).map(([key, value]) => (
            <div key={key} className="bg-black/20 rounded-lg p-3 border border-gray-700/50">
              <div className="text-xs text-gray-500">{key}</div>
              <div className="text-sm font-medium text-gray-200 mt-0.5">{value}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* 3. Performance Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <Card className="p-4">
          <div className="text-xs text-gray-500">Win Rate</div>
          <div className="text-xl font-bold text-blue-400 mt-1">
            {xpData ? `${(xpData.win_rate * 100).toFixed(1)}%` : strategy ? `${(strategy.win_rate * 100).toFixed(1)}%` : '--'}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-gray-500">Total P&L</div>
          <div className={`text-xl font-bold mt-1 ${(xpData?.total_profit ?? strategy?.total_profit ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${(xpData?.total_profit ?? strategy?.total_profit ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-gray-500">Avg Duration</div>
          <div className="text-xl font-bold text-gray-200 mt-1">
            {xpData ? formatDuration(xpData.avg_duration_seconds) : '--'}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-gray-500">Best Trade</div>
          <div className="text-xl font-bold text-green-400 mt-1">
            ${(xpData?.best_trade ?? 0).toFixed(2)}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-gray-500">Worst Trade</div>
          <div className="text-xl font-bold text-red-400 mt-1">
            ${(xpData?.worst_trade ?? 0).toFixed(2)}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-gray-500">Profit Factor</div>
          <div className="text-xl font-bold text-purple-400 mt-1">
            {strategy?.profit_factor?.toFixed(2) ?? '--'}
          </div>
        </Card>
      </div>

      {/* 4. Trade History */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">Recent Trades</h2>
        {trades.length === 0 ? (
          <p className="text-sm text-gray-500 italic">No trades recorded yet for this strategy.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 border-b border-gray-700">
                  <th className="pb-2 pr-4">Ticket</th>
                  <th className="pb-2 pr-4">Symbol</th>
                  <th className="pb-2 pr-4">Direction</th>
                  <th className="pb-2 pr-4">Entry</th>
                  <th className="pb-2 pr-4">Exit</th>
                  <th className="pb-2 pr-4">Lots</th>
                  <th className="pb-2 pr-4">P&L</th>
                  <th className="pb-2 pr-4">Duration</th>
                  <th className="pb-2">Time</th>
                </tr>
              </thead>
              <tbody>
                {trades.slice(0, 20).map((trade, idx) => (
                  <tr
                    key={trade.ticket || idx}
                    className="border-b border-gray-800 hover:bg-gray-800/30"
                  >
                    <td className="py-2 pr-4 text-gray-400">#{trade.ticket}</td>
                    <td className="py-2 pr-4 text-gray-200 font-medium">{trade.symbol}</td>
                    <td className="py-2 pr-4">
                      <span className={trade.direction === 'BUY' ? 'text-green-400' : 'text-red-400'}>
                        {trade.direction}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-gray-300">{trade.entry_price}</td>
                    <td className="py-2 pr-4 text-gray-300">{trade.exit_price}</td>
                    <td className="py-2 pr-4 text-gray-400">{trade.lots}</td>
                    <td className={`py-2 pr-4 font-semibold ${(trade.profit ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${trade.profit?.toFixed(2)}
                    </td>
                    <td className="py-2 pr-4 text-gray-400">
                      {trade.duration_seconds ? formatDuration(trade.duration_seconds) : '--'}
                    </td>
                    <td className="py-2 text-gray-500 text-xs">
                      {trade.closed_at ? new Date(trade.closed_at).toLocaleString() : '--'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* 5. RL Learning Progress */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">RL Learning Progress (Thompson Sampling)</h2>
        {rlDistributions.length === 0 ? (
          <p className="text-sm text-gray-500 italic">No RL distributions available yet. The system learns from trade outcomes.</p>
        ) : (
          <div className="space-y-4">
            {rlDistributions.map(dist => (
              <div key={dist.regime} className="bg-black/20 rounded-lg p-4 border border-gray-700/50">
                <div className="text-sm font-semibold text-gray-300 mb-3">
                  Regime: <span className="text-blue-400">{dist.regime}</span>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  {['conservative', 'moderate', 'aggressive'].map(preset => {
                    const presetData = dist[preset]
                    if (!presetData) return null
                    const ev = presetData.expected || 0
                    const barColor = ev >= 0.6 ? '#10B981' : ev >= 0.4 ? '#F59E0B' : '#EF4444'

                    return (
                      <div key={preset} className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-gray-400 capitalize">{preset}</span>
                          <span className="text-xs font-medium" style={{ color: barColor }}>
                            {(ev * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${ev * 100}%`,
                              backgroundColor: barColor,
                            }}
                          />
                        </div>
                        <div className="text-[10px] text-gray-600">
                          a={presetData.alpha} b={presetData.beta}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Confidence adjustment from RL */}
        {rlStats?.confidence_adjustments?.[code] && (
          <div className="mt-4 p-3 bg-black/20 rounded-lg border border-gray-700/50">
            <div className="text-xs text-gray-500 mb-1">RL Confidence Adjustment</div>
            <div className="flex items-center gap-3">
              <span className={`text-lg font-bold ${
                rlStats.confidence_adjustments[code].adjustment >= 0 ? 'text-green-400' : 'text-red-400'
              }`}>
                {rlStats.confidence_adjustments[code].adjustment >= 0 ? '+' : ''}
                {rlStats.confidence_adjustments[code].adjustment.toFixed(3)}
              </span>
              <span className="text-xs text-gray-400">
                {rlStats.confidence_adjustments[code].reason}
              </span>
            </div>
          </div>
        )}
      </Card>

      {/* 6. Badges & Achievements */}
      {xpData && (
        <Card className="p-6">
          <StrategyBadges badges={xpData.badges || []} />
        </Card>
      )}

      {/* 7. Skills Unlocked */}
      {xpData && xpData.skills_unlocked && xpData.skills_unlocked.length > 0 && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold text-gray-100 mb-3">Skills Unlocked</h2>
          <div className="flex flex-wrap gap-2">
            {xpData.skills_unlocked.map((skill, idx) => (
              <div
                key={idx}
                className="px-3 py-1.5 rounded-full text-xs font-medium border"
                style={{
                  color: xpData.level_color,
                  borderColor: `${xpData.level_color}30`,
                  backgroundColor: `${xpData.level_color}10`,
                }}
              >
                {skill}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 8. Current Parameters (from strategy config) */}
      {strategy?.config && Object.keys(strategy.config).length > 0 && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold text-gray-100 mb-3">Active Configuration</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {Object.entries(strategy.config).map(([key, value]) => (
              <div key={key} className="bg-black/20 rounded-lg p-3 border border-gray-700/50">
                <div className="text-xs text-gray-500">{key.replace(/_/g, ' ')}</div>
                <div className="text-sm font-medium text-gray-200 mt-0.5 font-mono">
                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
