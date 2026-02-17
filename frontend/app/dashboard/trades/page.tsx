'use client'

import { useState, useEffect } from 'react'
import { TradeFilters } from '@/components/trades/TradeFilters'
import { TradeTable } from '@/components/trades/TradeTable'
import { TradeStats } from '@/components/trades/TradeStats'

interface Trade {
  id: string
  date: string
  symbol: string
  direction: 'BUY' | 'SELL'
  lots: number
  entryPrice: number
  exitPrice: number | null
  pnl: number | null
  strategy: string
  status: 'open' | 'closed' | 'cancelled'
  entryTime: string
  exitTime?: string
  details?: string
}

interface FilterState {
  status: string
  strategy: string
  symbol: string
  dateFrom: string
  dateTo: string
}

// Mock data generator
const generateMockTrades = (): Trade[] => {
  const symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD']
  const strategies = ['STRATEGY_A', 'STRATEGY_B', 'STRATEGY_C', 'STRATEGY_D']
  const today = new Date()

  return Array.from({ length: 150 }, (_, i) => {
    const date = new Date(today)
    date.setDate(date.getDate() - i)
    const isClosed = Math.random() > 0.2
    const isWinning = Math.random() > 0.42

    return {
      id: `TRADE_${String(i + 1).padStart(4, '0')}`,
      date: date.toISOString().split('T')[0],
      symbol: symbols[Math.floor(Math.random() * symbols.length)],
      direction: Math.random() > 0.5 ? 'BUY' : 'SELL',
      lots: Math.round(Math.random() * 5 + 1),
      entryPrice: Math.random() * 2000 + 1,
      exitPrice: isClosed ? Math.random() * 2000 + 1 : null,
      pnl: isClosed ? (isWinning ? Math.random() * 500 + 50 : -(Math.random() * 300 + 20)) : null,
      strategy: strategies[Math.floor(Math.random() * strategies.length)],
      status: isClosed ? (Math.random() > 0.95 ? 'cancelled' : 'closed') : 'open',
      entryTime: `${String(Math.floor(Math.random() * 24)).padStart(2, '0')}:${String(Math.floor(Math.random() * 60)).padStart(2, '0')}:${String(Math.floor(Math.random() * 60)).padStart(2, '0')}`,
      exitTime: isClosed ? `${String(Math.floor(Math.random() * 24)).padStart(2, '0')}:${String(Math.floor(Math.random() * 60)).padStart(2, '0')}:${String(Math.floor(Math.random() * 60)).padStart(2, '0')}` : undefined,
    }
  })
}

export default function TradesPage() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [filteredTrades, setFilteredTrades] = useState<Trade[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [filters, setFilters] = useState<FilterState>({
    status: 'all',
    strategy: 'all',
    symbol: 'all',
    dateFrom: '',
    dateTo: '',
  })
  const [sortBy, setSortBy] = useState('date')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  // Fetch trades
  useEffect(() => {
    setTimeout(() => {
      setTrades(generateMockTrades())
      setIsLoading(false)
    }, 300)
  }, [])

  // Filter trades
  useEffect(() => {
    let result = [...trades]

    if (filters.status !== 'all') {
      result = result.filter(t => t.status === filters.status)
    }
    if (filters.strategy !== 'all') {
      result = result.filter(t => t.strategy === filters.strategy)
    }
    if (filters.symbol !== 'all') {
      result = result.filter(t => t.symbol === filters.symbol)
    }
    if (filters.dateFrom) {
      result = result.filter(t => new Date(t.date) >= new Date(filters.dateFrom))
    }
    if (filters.dateTo) {
      result = result.filter(t => new Date(t.date) <= new Date(filters.dateTo))
    }

    // Sort
    result.sort((a, b) => {
      let aVal: any = a[sortBy as keyof Trade]
      let bVal: any = b[sortBy as keyof Trade]

      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortOrder === 'asc' ? aVal - bVal : bVal - aVal
      }

      if (typeof aVal === 'string' && typeof bVal === 'string') {
        const cmp = aVal.localeCompare(bVal)
        return sortOrder === 'asc' ? cmp : -cmp
      }

      return 0
    })

    setFilteredTrades(result)
    setPage(1)
  }, [trades, filters, sortBy, sortOrder])

  const handleFilterChange = (newFilters: FilterState) => {
    setFilters(newFilters)
  }

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      setSortOrder('desc')
    }
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-100">Trades</h1>
        <p className="text-gray-400 mt-2">View and analyze your trading history</p>
      </div>

      {/* Trade Statistics */}
      <TradeStats filters={filters} />

      {/* Filters */}
      <TradeFilters onFilterChange={handleFilterChange} />

      {/* Trade Table */}
      <TradeTable
        trades={filteredTrades}
        isLoading={isLoading}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onSort={handleSort}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
      />
    </div>
  )
}
