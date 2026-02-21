'use client'

import React, { useEffect, useState, useCallback, useMemo } from 'react'
import { AccountCard } from '@/components/dashboard/AccountCard'
import { EquityChart } from '@/components/dashboard/EquityChart'
import { RegimeCard } from '@/components/dashboard/RegimeCard'
import { StrategyCards } from '@/components/dashboard/StrategyCards'
import { RecentTrades } from '@/components/dashboard/RecentTrades'
import { SystemStatus } from '@/components/dashboard/SystemStatus'
import { SkeletonGrid } from '@/components/ui/Skeleton'
import { useDashboard } from '@/hooks'
import { getHealth } from '@/lib/api'
import type { HealthCheck } from '@/lib/types'

// Use relative URLs so requests go through Caddy reverse proxy (same origin)
// Do NOT use NEXT_PUBLIC_API_URL here -- it gets baked at build time as
// "http://localhost:8000" which resolves to the user's machine, not the VPS.

export default function DashboardPage() {
  const { dashboard, isLoading, error, refresh } = useDashboard()
  const [healthData, setHealthData] = useState<HealthCheck | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const fetchHealth = useCallback(async () => {
    try {
      const data = await getHealth()
      setHealthData(data)
    } catch {
      // Health endpoint is supplemental; don't block the dashboard
    }
    setLastUpdate(new Date())
  }, [])

  // Fetch health on mount + auto-refresh every 10 seconds
  useEffect(() => {
    fetchHealth()
    const interval = setInterval(fetchHealth, 10000)
    return () => clearInterval(interval)
  }, [fetchHealth])

  const handleRefresh = async () => {
    await Promise.all([refresh(), fetchHealth()])
  }

  // Transform backend data to component props
  const accountProps = dashboard?.account ? {
    balance: dashboard.account.balance || 0,
    equity: dashboard.account.equity || 0,
    freeMargin: dashboard.account.free_margin || 0,
    marginLevel: dashboard.account.margin_level || 0,
    drawdownPct: dashboard.account.drawdown_pct || 0,
    profit: dashboard.floating_profit ?? dashboard.account.profit ?? 0,
    leverage: dashboard.account.leverage || 0,
    currency: dashboard.account.currency || 'USD',
    login: dashboard.account.login ?? undefined,
    server: dashboard.account.server ?? undefined,
  } : null

  const strategyProps = (dashboard?.strategies || []).map((s: any) => ({
    name: s.name || `Strategy ${s.code}`,
    code: s.code,
    status: s.status || 'active',
    allocation: s.allocation_pct || 0,
    winRate: s.win_rate || 0,
    pnl: s.total_profit || 0,
    totalTrades: s.total_trades || 0,
    profitFactor: s.profit_factor || 0,
  }))

  const tradeProps = (dashboard?.recent_trades || []).map((t: any) => ({
    id: t.id,
    time: t.opened_at || t.closed_at || '',
    symbol: t.symbol,
    direction: t.direction,
    lots: t.lots,
    entry: t.entry_price || 0,
    exit: t.exit_price || 0,
    pnl: t.net_profit ?? t.profit ?? 0,
    status: t.status,
  }))

  // Build system status from health check
  const systemProps = healthData ? {
    services: Object.entries(healthData.services || {}).map(([name, info]: [string, any]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1),
      status: info.status === 'connected' ? 'up' as const : 'down' as const,
    })),
    uptime: healthData.uptime_seconds || 0,
    version: healthData.version || '1.0.0',
    overallStatus: healthData.status,
    dryRun: healthData.trading?.dry_run,
    // Prefer unified value from dashboard payload; fall back to health endpoint.
    openPositions:
      dashboard?.open_positions ??
      healthData.trading?.open_positions ??
      dashboard?.positions?.length ??
      0,
  } : null

  const formatPositionPrice = (value: number | null | undefined) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return 'N/A'
    }
    const price = Number(value)
    const abs = Math.abs(price)
    if (abs >= 1000) return price.toFixed(2)
    if (abs >= 100) return price.toFixed(3)
    return price.toFixed(5)
  }

  const formatPositionProfit = (value: number | null | undefined) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return 'N/A'
    }
    const pnl = Number(value)
    const sign = pnl > 0 ? '+' : ''
    return `${sign}${pnl.toFixed(2)}`
  }

  const getPositionProfitColor = (value: number | null | undefined) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return 'text-gray-400'
    }
    if (Number(value) > 0) return 'text-brand-accent-green'
    if (Number(value) < 0) return 'text-brand-accent-red'
    return 'text-gray-200'
  }

  const groupedPositions = useMemo(() => {
    const groups = new Map<string, { key: string; code: string; name: string; rows: any[] }>()
    const rows = dashboard?.positions || []

    for (const pos of rows) {
      const strategyCode = typeof pos?.strategy_code === 'string' && pos.strategy_code.trim().length > 0
        ? pos.strategy_code.toUpperCase()
        : 'UNASSIGNED'
      const strategyName = typeof pos?.strategy_name === 'string' && pos.strategy_name.trim().length > 0
        ? pos.strategy_name
        : (strategyCode === 'UNASSIGNED' ? 'Unassigned Strategy' : strategyCode)

      if (!groups.has(strategyCode)) {
        groups.set(strategyCode, {
          key: strategyCode,
          code: strategyCode,
          name: strategyName,
          rows: [],
        })
      }
      groups.get(strategyCode)!.rows.push(pos)
    }

    return Array.from(groups.values()).sort((a, b) => a.code.localeCompare(b.code))
  }, [dashboard?.positions])

  const getGroupProfit = (rows: any[]) => {
    let total = 0
    let hasNumericProfit = false
    for (const row of rows) {
      if (row?.profit === null || row?.profit === undefined || Number.isNaN(Number(row.profit))) {
        continue
      }
      hasNumericProfit = true
      total += Number(row.profit)
    }
    return hasNumericProfit ? Number(total.toFixed(2)) : null
  }

  return (
    <div className="min-h-screen bg-brand-dark p-4 md:p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl md:text-4xl font-bold text-gray-100">Dashboard</h1>
            <p className="text-gray-400 text-sm mt-1">
              {lastUpdate ? `Last updated: ${lastUpdate.toLocaleTimeString()}` : 'Loading...'}
              {dashboard?.dry_run === false && (
                <span className="ml-2 text-brand-accent-green font-semibold">LIVE</span>
              )}
              {dashboard?.dry_run === true && (
                <span className="ml-2 text-yellow-400 font-semibold">DRY RUN</span>
              )}
            </p>
          </div>
          <button
            onClick={handleRefresh}
            disabled={isLoading}
            className="px-4 py-2 bg-brand-accent-green text-brand-dark rounded-lg font-semibold hover:bg-opacity-90 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        {/* Error State */}
        {error && (
          <div className="mb-6 p-4 bg-red-900/20 border border-red-700/50 rounded-lg text-red-400">
            <p className="text-sm">{error}</p>
            <button
              onClick={handleRefresh}
              className="mt-2 text-xs text-red-300 hover:text-red-200 underline"
            >
              Try again
            </button>
          </div>
        )}

        {/* Loading State */}
        {isLoading && !dashboard && !healthData ? (
          <SkeletonGrid />
        ) : (
          <>
            {/* Top Row: Account & Regime */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6 mb-6">
              <div className="lg:col-span-2">
                <AccountCard data={accountProps} />
              </div>
              <RegimeCard data={dashboard?.regime ? { ...dashboard.regime, lastDetected: dashboard.regime.lastDetected ?? undefined } : undefined} />
            </div>

            {/* Open Positions */}
            {((dashboard?.positions?.length ?? 0) > 0) && (
              <div className="mb-6 p-4 bg-brand-panel border border-gray-700 rounded-lg">
                <h3 className="text-lg font-semibold text-gray-100 mb-3">Open Positions ({dashboard!.positions!.length})</h3>
                {(dashboard?.open_positions_source === 'db' || dashboard?.open_positions_source === 'hybrid') && (
                  <p className="text-xs text-yellow-400 mb-3">
                    Open P/L is estimated from live ticks while MT5 positions feed is unavailable.
                  </p>
                )}
                <div className="space-y-3">
                  {groupedPositions.map((group) => {
                    const groupProfit = getGroupProfit(group.rows)
                    return (
                      <details key={group.key} open className="border border-gray-700/70 rounded-lg overflow-hidden bg-black/10">
                        <summary className="list-none cursor-pointer px-4 py-3 flex items-center justify-between hover:bg-black/20 transition-colors [&::-webkit-details-marker]:hidden">
                          <div className="flex items-center gap-3 min-w-0">
                            <span className="text-sm font-semibold text-gray-100 truncate">{group.code}</span>
                            <span className="text-xs text-gray-400 truncate">{group.name}</span>
                            <span className="text-xs text-gray-500">{group.rows.length} positions</span>
                          </div>
                          <span className={`text-sm font-semibold ${getPositionProfitColor(groupProfit)}`}>
                            {formatPositionProfit(groupProfit)}
                          </span>
                        </summary>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-gray-700">
                                <th className="px-3 py-2 text-left text-xs text-gray-400">Ticket</th>
                                <th className="px-3 py-2 text-left text-xs text-gray-400">Symbol</th>
                                <th className="px-3 py-2 text-left text-xs text-gray-400">Type</th>
                                <th className="px-3 py-2 text-right text-xs text-gray-400">Lots</th>
                                <th className="px-3 py-2 text-right text-xs text-gray-400">Open Price</th>
                                <th className="px-3 py-2 text-right text-xs text-gray-400">Current</th>
                                <th className="px-3 py-2 text-right text-xs text-gray-400">Profit</th>
                              </tr>
                            </thead>
                            <tbody>
                              {group.rows.map((pos: any) => (
                                <tr key={pos.ticket} className="border-b border-gray-800">
                                  <td className="px-3 py-2 text-gray-300">{pos.ticket}</td>
                                  <td className="px-3 py-2 font-semibold text-gray-100">{pos.symbol}</td>
                                  <td className={`px-3 py-2 ${pos.type === 'BUY' ? 'text-brand-accent-green' : 'text-brand-accent-red'}`}>{pos.type}</td>
                                  <td className="px-3 py-2 text-right text-gray-300">{Number(pos.lots || 0).toFixed(2)}</td>
                                  <td className="px-3 py-2 text-right text-gray-400">{formatPositionPrice(pos.price_open)}</td>
                                  <td className="px-3 py-2 text-right text-gray-400">{formatPositionPrice(pos.price_current)}</td>
                                  <td className={`px-3 py-2 text-right font-semibold ${getPositionProfitColor(pos.profit)}`}>
                                    {formatPositionProfit(pos.profit)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </details>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Equity Chart */}
            <div className="mb-6">
              <EquityChart data={dashboard?.equity_curve?.map((p: any) => ({ timestamp: p.timestamp, value: p.equity ?? p.value ?? 0 }))} />
            </div>

            {/* Strategies & System Status */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6 mb-6">
              <StrategyCards strategies={strategyProps.length > 0 ? strategyProps : undefined} />
              <SystemStatus data={systemProps} />
            </div>

            {/* Recent Trades */}
            <div>
              <RecentTrades trades={tradeProps.length > 0 ? tradeProps : undefined} />
            </div>

            {/* Footer Info */}
            <div className="mt-8 p-4 bg-brand-panel border border-gray-700 rounded-lg text-center text-gray-400 text-xs">
              <p>
                JSR Hydra v{dashboard?.version || healthData?.version || '1.0.0'}
                {' '}&bull;{' '}Auto-refresh every 10 seconds
                {dashboard?.system_status && ` \u2022 Status: ${dashboard.system_status}`}
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
