'use client'

import { useState, useEffect } from 'react'
import { ChevronDown } from 'lucide-react'
import { Card } from '@/components/ui/Card'

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

interface TradeTableProps {
  trades: Trade[]
  isLoading?: boolean
  sortBy?: string
  sortOrder?: 'asc' | 'desc'
  onSort?: (field: string) => void
  page?: number
  pageSize?: number
  onPageChange?: (page: number) => void
  onPageSizeChange?: (size: number) => void
}

export function TradeTable({
  trades,
  isLoading = false,
  sortBy = 'date',
  sortOrder = 'desc',
  onSort,
  page = 1,
  pageSize = 10,
  onPageChange,
  onPageSizeChange,
}: TradeTableProps) {
  const [expandedTradeId, setExpandedTradeId] = useState<string | null>(null)

  const SortHeader = ({ field, label }: { field: string; label: string }) => (
    <button
      onClick={() => onSort?.(field)}
      className="flex items-center gap-2 hover:text-brand-accent-green transition-colors"
    >
      {label}
      {sortBy === field && (
        <span className="text-xs">{sortOrder === 'asc' ? '↑' : '↓'}</span>
      )}
    </button>
  )

  const totalPages = Math.ceil(trades.length / pageSize)
  const startIdx = (page - 1) * pageSize
  const endIdx = startIdx + pageSize
  const paginatedTrades = trades.slice(startIdx, endIdx)

  return (
    <Card className="space-y-4">
      {/* Page Size Selector */}
      <div className="flex justify-end">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">Show</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange?.(parseInt(e.target.value))}
            className="px-2 py-1 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-brand-accent-green focus:outline-none"
          >
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
          </select>
          <span className="text-sm text-gray-400">per page</span>
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="text-center py-8 text-gray-400">
          Loading trades...
        </div>
      ) : trades.length === 0 ? (
        <div className="text-center py-8 text-gray-400">
          No trades found
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left px-4 py-3 text-gray-400 font-medium w-8"></th>
                  <th className="text-left px-4 py-3 text-gray-400 font-medium">
                    <SortHeader field="date" label="Date" />
                  </th>
                  <th className="text-left px-4 py-3 text-gray-400 font-medium">
                    <SortHeader field="symbol" label="Symbol" />
                  </th>
                  <th className="text-center px-4 py-3 text-gray-400 font-medium">
                    Direction
                  </th>
                  <th className="text-right px-4 py-3 text-gray-400 font-medium">
                    <SortHeader field="lots" label="Lots" />
                  </th>
                  <th className="text-right px-4 py-3 text-gray-400 font-medium">
                    <SortHeader field="entryPrice" label="Entry" />
                  </th>
                  <th className="text-right px-4 py-3 text-gray-400 font-medium">
                    <SortHeader field="exitPrice" label="Exit" />
                  </th>
                  <th className="text-right px-4 py-3 text-gray-400 font-medium">
                    <SortHeader field="pnl" label="P&L" />
                  </th>
                  <th className="text-left px-4 py-3 text-gray-400 font-medium">Strategy</th>
                  <th className="text-center px-4 py-3 text-gray-400 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {paginatedTrades.map((trade) => (
                  <tr
                    key={trade.id}
                    className="border-b border-gray-700 hover:bg-gray-800/50 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setExpandedTradeId(expandedTradeId === trade.id ? null : trade.id)}
                        className="text-gray-400 hover:text-gray-200"
                      >
                        <ChevronDown
                          size={16}
                          className={`transition-transform ${expandedTradeId === trade.id ? 'rotate-180' : ''}`}
                        />
                      </button>
                    </td>
                    <td className="px-4 py-3 text-gray-300">{trade.date}</td>
                    <td className="px-4 py-3 font-semibold text-gray-100">{trade.symbol}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                        trade.direction === 'BUY'
                          ? 'bg-green-900/30 text-green-400'
                          : 'bg-red-900/30 text-red-400'
                      }`}>
                        {trade.direction}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300">{trade.lots.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-gray-300">
                      {trade.entryPrice.toFixed(5)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300">
                      {trade.exitPrice ? trade.exitPrice.toFixed(5) : '-'}
                    </td>
                    <td className={`px-4 py-3 text-right font-semibold ${
                      trade.pnl !== null
                        ? trade.pnl >= 0
                          ? 'text-green-400'
                          : 'text-red-400'
                        : 'text-gray-400'
                    }`}>
                      {trade.pnl !== null ? `$${trade.pnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{trade.strategy}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                        trade.status === 'open'
                          ? 'bg-blue-900/30 text-blue-400'
                          : trade.status === 'closed'
                          ? 'bg-gray-700/30 text-gray-300'
                          : 'bg-red-900/30 text-red-400'
                      }`}>
                        {trade.status.charAt(0).toUpperCase() + trade.status.slice(1)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Expanded Trade Details */}
          {expandedTradeId && (
            <div className="border-t border-gray-700 mt-4 pt-4">
              {paginatedTrades.find(t => t.id === expandedTradeId) && (
                <div className="bg-black/20 p-4 rounded-lg space-y-2">
                  <div className="text-sm text-gray-300">
                    <p><span className="text-gray-500">Entry Time:</span> {paginatedTrades.find(t => t.id === expandedTradeId)?.entryTime}</p>
                    {paginatedTrades.find(t => t.id === expandedTradeId)?.exitTime && (
                      <p><span className="text-gray-500">Exit Time:</span> {paginatedTrades.find(t => t.id === expandedTradeId)?.exitTime}</p>
                    )}
                    {paginatedTrades.find(t => t.id === expandedTradeId)?.details && (
                      <p><span className="text-gray-500">Details:</span> {paginatedTrades.find(t => t.id === expandedTradeId)?.details}</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Pagination */}
          <div className="flex items-center justify-between pt-4 border-t border-gray-700">
            <div className="text-sm text-gray-400">
              Showing {startIdx + 1} to {Math.min(endIdx, trades.length)} of {trades.length} trades
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => onPageChange?.(Math.max(1, page - 1))}
                disabled={page === 1}
                className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-300 hover:bg-gray-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                Previous
              </button>
              <div className="flex items-center gap-2">
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  const pageNum = i + 1
                  return (
                    <button
                      key={pageNum}
                      onClick={() => onPageChange?.(pageNum)}
                      className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                        page === pageNum
                          ? 'bg-brand-accent-green text-brand-dark'
                          : 'bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700'
                      }`}
                    >
                      {pageNum}
                    </button>
                  )
                })}
                {totalPages > 5 && <span className="text-gray-500">...</span>}
              </div>
              <button
                onClick={() => onPageChange?.(Math.min(totalPages, page + 1))}
                disabled={page === totalPages}
                className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-300 hover:bg-gray-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </Card>
  )
}
