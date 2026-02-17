'use client'

import { useState } from 'react'
import { X } from 'lucide-react'
import { Card } from '@/components/ui/Card'

interface TradeFiltersProps {
  onFilterChange?: (filters: FilterState) => void
}

interface FilterState {
  status: string
  strategy: string
  symbol: string
  dateFrom: string
  dateTo: string
}

const STATUS_OPTIONS = ['all', 'open', 'closed', 'cancelled']
const STRATEGY_OPTIONS = ['all', 'STRATEGY_A', 'STRATEGY_B', 'STRATEGY_C', 'STRATEGY_D']
const SYMBOL_OPTIONS = ['all', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD']

export function TradeFilters({ onFilterChange }: TradeFiltersProps) {
  const [filters, setFilters] = useState<FilterState>({
    status: 'all',
    strategy: 'all',
    symbol: 'all',
    dateFrom: '',
    dateTo: '',
  })

  const handleFilterChange = (key: keyof FilterState, value: string) => {
    const newFilters = { ...filters, [key]: value }
    setFilters(newFilters)
    onFilterChange?.(newFilters)
  }

  const handleClearFilters = () => {
    const emptyFilters = {
      status: 'all',
      strategy: 'all',
      symbol: 'all',
      dateFrom: '',
      dateTo: '',
    }
    setFilters(emptyFilters)
    onFilterChange?.(emptyFilters)
  }

  const hasActiveFilters =
    filters.status !== 'all' ||
    filters.strategy !== 'all' ||
    filters.symbol !== 'all' ||
    filters.dateFrom !== '' ||
    filters.dateTo !== ''

  return (
    <Card className="p-6">
      <div className="grid grid-cols-1 md:grid-cols-6 gap-4 items-end">
        {/* Status Filter */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Status
          </label>
          <select
            value={filters.status}
            onChange={(e) => handleFilterChange('status', e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 text-sm focus:border-brand-accent-green focus:outline-none"
          >
            {STATUS_OPTIONS.map(status => (
              <option key={status} value={status}>
                {status.charAt(0).toUpperCase() + status.slice(1)}
              </option>
            ))}
          </select>
        </div>

        {/* Strategy Filter */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Strategy
          </label>
          <select
            value={filters.strategy}
            onChange={(e) => handleFilterChange('strategy', e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 text-sm focus:border-brand-accent-green focus:outline-none"
          >
            {STRATEGY_OPTIONS.map(strat => (
              <option key={strat} value={strat}>
                {strat}
              </option>
            ))}
          </select>
        </div>

        {/* Symbol Filter */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Symbol
          </label>
          <select
            value={filters.symbol}
            onChange={(e) => handleFilterChange('symbol', e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 text-sm focus:border-brand-accent-green focus:outline-none"
          >
            {SYMBOL_OPTIONS.map(symbol => (
              <option key={symbol} value={symbol}>
                {symbol}
              </option>
            ))}
          </select>
        </div>

        {/* Date From */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            From Date
          </label>
          <input
            type="date"
            value={filters.dateFrom}
            onChange={(e) => handleFilterChange('dateFrom', e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 text-sm focus:border-brand-accent-green focus:outline-none"
          />
        </div>

        {/* Date To */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            To Date
          </label>
          <input
            type="date"
            value={filters.dateTo}
            onChange={(e) => handleFilterChange('dateTo', e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 text-sm focus:border-brand-accent-green focus:outline-none"
          />
        </div>

        {/* Clear Button */}
        <div>
          <button
            onClick={handleClearFilters}
            disabled={!hasActiveFilters}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-300 hover:bg-gray-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
          >
            <X size={16} />
            Clear
          </button>
        </div>
      </div>
    </Card>
  )
}
