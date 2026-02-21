'use client'

import React, { useState, useEffect, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { TradeStats } from '@/components/trades/TradeStats'

interface Trade {
  id: string
  symbol: string
  strategy_code?: string | null
  strategy_name?: string | null
  direction: 'BUY' | 'SELL'
  lots: number
  entry_price: number
  exit_price: number | null
  profit: number
  net_profit: number
  status: string
  opened_at: string
  closed_at: string | null
}

interface ApiResponse {
  trades: Trade[]
  total: number
  page: number
  per_page: number
}

interface StrategyOption {
  code: string
  name: string
}

export default function TradesPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [trades, setTrades] = useState<Trade[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filter and pagination state
  const [statusFilter, setStatusFilter] = useState('')
  const [symbolFilter, setSymbolFilter] = useState('')
  const [strategyFilter, setStrategyFilter] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [totalTrades, setTotalTrades] = useState(0)
  const [perPage, setPerPage] = useState(20)

  // Available symbols for filter (fetched once, not derived from current page)
  const [symbols, setSymbols] = useState<string[]>([])
  const [strategies, setStrategies] = useState<StrategyOption[]>([])
  const symbolsFetched = useRef(false)

  const strategyFromUrl = (searchParams.get('strategy') || '').toUpperCase()

  useEffect(() => {
    if (!strategyFromUrl) return
    setStrategyFilter(strategyFromUrl)
    setCurrentPage(1)
  }, [strategyFromUrl])

  useEffect(() => {
    const fetchStrategies = async () => {
      try {
        const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
        const headers: Record<string, string> = { Accept: 'application/json' }
        if (token) headers.Authorization = `Bearer ${token}`

        const response = await fetch('/api/strategies', { headers })
        if (!response.ok) return
        const data = await response.json()
        const options = (data || [])
          .map((strategy: any) => ({
            code: String(strategy.code || '').toUpperCase(),
            name: strategy.name || `Strategy ${strategy.code}`,
          }))
          .filter((strategy: StrategyOption) => strategy.code)
          .sort((a: StrategyOption, b: StrategyOption) => a.code.localeCompare(b.code))
        setStrategies(options)
      } catch {
        // Non-critical, trade history still works.
      }
    }

    fetchStrategies()
  }, [])

  // Fetch all available symbols once for the filter dropdown
  useEffect(() => {
    if (symbolsFetched.current) return
    symbolsFetched.current = true

    const fetchSymbols = async () => {
      try {
        const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (token) headers['Authorization'] = `Bearer ${token}`

        const response = await fetch('/api/trades?per_page=100', { headers })
        if (response.ok) {
          const data: ApiResponse = await response.json()
          const uniqueSymbols = Array.from(new Set(data.trades.map(t => t.symbol))).sort()
          setSymbols(uniqueSymbols)
        }
      } catch {
        // Symbols filter will just be empty; non-critical
      }
    }
    fetchSymbols()
  }, [])

  // Fetch trades from API
  const fetchTrades = async (
    status?: string,
    symbol?: string,
    strategyCode?: string,
    page?: number,
  ) => {
    try {
      setIsLoading(true)
      setError(null)

      const params = new URLSearchParams()
      if (status) params.append('status_filter', status)
      if (symbol) params.append('symbol_filter', symbol)
      if (strategyCode) params.append('strategy_filter', strategyCode)
      params.append('per_page', perPage.toString())
      params.append('page', (page || 1).toString())

      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (token) headers['Authorization'] = `Bearer ${token}`

      const response = await fetch(`/api/trades?${params.toString()}`, { headers })
      if (!response.ok) {
        if (response.status === 401) {
          if (typeof window !== 'undefined') {
            localStorage.removeItem('auth_token')
            window.location.href = '/login'
          }
        }
        throw new Error('Failed to fetch trades')
      }

      const data: ApiResponse = await response.json()
      setTrades(data.trades)
      setTotalTrades(data.total)
      setCurrentPage(data.page)
      setPerPage(data.per_page)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
      setTrades([])
    } finally {
      setIsLoading(false)
    }
  }

  // Fetch when filters or page changes (single effect, no duplicate on mount)
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchTrades(
        statusFilter || undefined,
        symbolFilter || undefined,
        strategyFilter || undefined,
        currentPage
      )
    }, 300)
    return () => clearTimeout(timer)
  }, [statusFilter, symbolFilter, strategyFilter, currentPage, perPage])

  const updateStrategyInUrl = (code: string) => {
    const params = new URLSearchParams(searchParams.toString())
    if (code) {
      params.set('strategy', code)
    } else {
      params.delete('strategy')
    }
    const query = params.toString()
    router.replace(query ? `/dashboard/trades?${query}` : '/dashboard/trades')
  }

  const totalPages = Math.ceil(totalTrades / perPage)

  const formatPrice = (price: number | null | undefined) => {
    if (price === null || price === undefined) return '-'
    return price.toFixed(5)
  }

  const formatPnL = (pnl: number | null | undefined) => {
    if (pnl === null || pnl === undefined) return '-'
    const sign = pnl >= 0 ? '+' : ''
    return `${sign}${pnl.toFixed(2)}`
  }

  const getPnLColor = (pnl: number | null | undefined) => {
    if (pnl === null || pnl === undefined) return 'text-gray-400'
    return pnl >= 0 ? 'text-green-400' : 'text-red-400'
  }

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return '-'
    try {
      const d = new Date(dateStr)
      return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
        + ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
    } catch {
      return dateStr
    }
  }

  const getStatusColor = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'OPEN':
        return 'bg-blue-900/50 text-blue-200'
      case 'CLOSED':
        return 'bg-gray-700/50 text-gray-200'
      case 'CANCELLED':
        return 'bg-red-900/50 text-red-200'
      case 'PENDING':
        return 'bg-yellow-900/50 text-yellow-200'
      default:
        return 'bg-gray-700/50 text-gray-200'
    }
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-100">Trades</h1>
        <p className="text-gray-400 mt-2">View and analyze your trading history</p>
        {strategyFilter && (
          <p className="text-sm text-blue-300 mt-2">
            Filtered to strategy {strategyFilter}
          </p>
        )}
      </div>

      {/* Filters */}
      <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Status Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Status</label>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value)
                setCurrentPage(1)
              }}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500"
            >
              <option value="">All Statuses</option>
              <option value="OPEN">Open</option>
              <option value="CLOSED">Closed</option>
              <option value="PENDING">Pending</option>
            </select>
          </div>

          {/* Strategy Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Strategy</label>
            <select
              value={strategyFilter}
              onChange={(e) => {
                const code = e.target.value
                setStrategyFilter(code)
                setCurrentPage(1)
                updateStrategyInUrl(code)
              }}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500"
            >
              <option value="">All Strategies</option>
              {strategies.map((strategy) => (
                <option key={strategy.code} value={strategy.code}>
                  {strategy.code} - {strategy.name}
                </option>
              ))}
            </select>
          </div>

          {/* Symbol Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Symbol</label>
            <select
              value={symbolFilter}
              onChange={(e) => {
                setSymbolFilter(e.target.value)
                setCurrentPage(1)
              }}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500"
            >
              <option value="">All Symbols</option>
              {symbols.map(symbol => (
                <option key={symbol} value={symbol}>{symbol}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Trade Stats Summary */}
      <TradeStats filters={strategyFilter ? { strategy: strategyFilter } : undefined} />

      {/* Error Message */}
      {error && (
        <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 text-red-200">
          {error}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && trades.length === 0 && (
        <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-12 text-center">
          <p className="text-gray-400">No trades recorded yet. The engine will log trades as they execute.</p>
        </div>
      )}

      {/* Trades Table */}
      {trades.length > 0 && (
        <>
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700 bg-gray-900/50">
                    <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Date</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Symbol</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Strategy</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Direction</th>
                    <th className="px-6 py-3 text-right text-sm font-semibold text-gray-300">Lots</th>
                    <th className="px-6 py-3 text-right text-sm font-semibold text-gray-300">Entry</th>
                    <th className="px-6 py-3 text-right text-sm font-semibold text-gray-300">Exit</th>
                    <th className="px-6 py-3 text-right text-sm font-semibold text-gray-300">P&L</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-gray-300">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr>
                      <td colSpan={9} className="px-6 py-8 text-center text-gray-400">
                        Loading trades...
                      </td>
                    </tr>
                  ) : (
                    trades.map((trade) => (
                      <tr key={trade.id} className="border-b border-gray-700 hover:bg-gray-700/30 transition-colors">
                        <td className="px-6 py-4 text-sm text-gray-300">{formatDate(trade.opened_at)}</td>
                        <td className="px-6 py-4 text-sm font-medium text-gray-100">{trade.symbol}</td>
                        <td className="px-6 py-4 text-sm text-gray-300">
                          {trade.strategy_code || '-'}
                          {trade.strategy_name ? ` (${trade.strategy_name})` : ''}
                        </td>
                        <td className="px-6 py-4 text-sm">
                          <span className={trade.direction === 'BUY' ? 'text-green-400' : 'text-red-400'}>
                            {trade.direction}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-right text-gray-300">{trade.lots ?? '-'}</td>
                        <td className="px-6 py-4 text-sm text-right text-gray-300">{formatPrice(trade.entry_price)}</td>
                        <td className="px-6 py-4 text-sm text-right text-gray-300">{formatPrice(trade.exit_price)}</td>
                        <td className={`px-6 py-4 text-sm text-right font-medium ${getPnLColor(trade.net_profit)}`}>
                          {formatPnL(trade.net_profit)}
                        </td>
                        <td className="px-6 py-4 text-sm">
                          <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(trade.status)}`}>
                            {trade.status?.toUpperCase() ?? 'UNKNOWN'}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between bg-gray-800/50 border border-gray-700 rounded-lg p-4">
              <div className="text-sm text-gray-400">
                Showing {(currentPage - 1) * perPage + 1} to {Math.min(currentPage * perPage, totalTrades)} of {totalTrades} trades
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                  disabled={currentPage === 1}
                  className="px-4 py-2 rounded bg-gray-700 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-600 transition-colors"
                >
                  Previous
                </button>

                <div className="flex items-center gap-2">
                  {Array.from({ length: totalPages }, (_, i) => i + 1)
                    .filter(page => {
                      const diff = Math.abs(page - currentPage)
                      return diff === 0 || diff === 1 || page === 1 || page === totalPages
                    })
                    .flatMap((page, idx, arr) => {
                      const elements: React.ReactNode[] = []
                      if (idx > 0 && arr[idx - 1] !== page - 1) {
                        elements.push(<span key={`dots-${page}`} className="text-gray-500 px-1">...</span>)
                      }
                      elements.push(
                        <button
                          key={page}
                          onClick={() => setCurrentPage(page)}
                          className={`px-3 py-2 rounded transition-colors ${
                            currentPage === page
                              ? 'bg-blue-600 text-white'
                              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                          }`}
                        >
                          {page}
                        </button>
                      )
                      return elements
                    })}
                </div>

                <button
                  onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                  disabled={currentPage === totalPages}
                  className="px-4 py-2 rounded bg-gray-700 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-600 transition-colors"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
