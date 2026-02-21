'use client'

import React, { useState } from 'react'

interface CellData {
  wins: number
  losses: number
  total: number
  profit: number
}

interface HeatmapProps {
  data: Record<string, Record<string, CellData>>
  rowLabels: string[]
  colLabels: string[]
  title: string
}

interface TooltipState {
  visible: boolean
  x: number
  y: number
  content: {
    winRate: number
    total: number
    profit: number
    row: string
    col: string
  } | null
}

function getCellStyle(cell: CellData | undefined): {
  bgClass: string
  opacity: number
  winRate: number
} {
  if (!cell || cell.total < 3) {
    return { bgClass: 'bg-gray-800', opacity: 0.4, winRate: 0 }
  }

  const winRate = cell.total > 0 ? cell.wins / cell.total : 0
  // Scale opacity based on sample size: 3 trades = 0.4, 20+ trades = 1.0
  const opacity = Math.min(1.0, 0.4 + (cell.total - 3) / 20 * 0.6)

  let bgClass: string
  if (winRate < 0.4) {
    bgClass = 'bg-red-500/30'
  } else if (winRate <= 0.6) {
    bgClass = 'bg-yellow-500/20'
  } else {
    bgClass = 'bg-[#00d97e]/30'
  }

  return { bgClass, opacity, winRate }
}

function getCellTextColor(winRate: number, total: number): string {
  if (total < 3) return 'text-gray-600'
  if (winRate < 0.4) return 'text-red-300'
  if (winRate <= 0.6) return 'text-yellow-300'
  return 'text-[#00d97e]'
}

export function PatternHeatmap({ data, rowLabels, colLabels, title }: HeatmapProps) {
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false,
    x: 0,
    y: 0,
    content: null,
  })

  const handleMouseEnter = (
    e: React.MouseEvent<HTMLDivElement>,
    row: string,
    col: string,
    cell: CellData | undefined,
  ) => {
    if (!cell || cell.total < 3) return
    const rect = e.currentTarget.getBoundingClientRect()
    const winRate = cell.total > 0 ? cell.wins / cell.total : 0
    setTooltip({
      visible: true,
      x: rect.left + rect.width / 2,
      y: rect.top - 8,
      content: {
        winRate,
        total: cell.total,
        profit: cell.profit,
        row,
        col,
      },
    })
  }

  const handleMouseLeave = () => {
    setTooltip((prev) => ({ ...prev, visible: false }))
  }

  return (
    <div className="relative">
      <h4 className="text-sm font-semibold text-gray-300 mb-3">{title}</h4>

      {/* Scrollable container for mobile */}
      <div className="overflow-x-auto">
        <div style={{ minWidth: `${colLabels.length * 56 + 80}px` }}>
          {/* Column headers */}
          <div className="flex mb-1">
            {/* Row label spacer */}
            <div className="w-20 shrink-0" />
            {colLabels.map((col) => (
              <div
                key={col}
                className="flex-1 text-center text-[10px] text-gray-500 font-mono px-0.5 truncate"
                style={{ minWidth: '48px' }}
              >
                {col}
              </div>
            ))}
          </div>

          {/* Rows */}
          {rowLabels.map((row) => (
            <div key={row} className="flex mb-1 items-center">
              {/* Row label */}
              <div className="w-20 shrink-0 text-right pr-2 text-[10px] text-gray-500 font-mono truncate">
                {row}
              </div>

              {/* Cells */}
              {colLabels.map((col) => {
                const cell = data[row]?.[col]
                const { bgClass, opacity, winRate } = getCellStyle(cell)
                const textColor = getCellTextColor(winRate, cell?.total ?? 0)
                const hasData = cell && cell.total >= 3

                return (
                  <div
                    key={col}
                    className="flex-1 mr-0.5 last:mr-0 relative"
                    style={{ minWidth: '48px' }}
                  >
                    <div
                      onMouseEnter={(e) => handleMouseEnter(e, row, col, cell)}
                      onMouseLeave={handleMouseLeave}
                      className={`
                        ${bgClass} rounded
                        flex items-center justify-center
                        h-9 cursor-default transition-all duration-150
                        border border-gray-800/60
                        ${hasData ? 'hover:brightness-125 hover:border-gray-600' : ''}
                      `}
                      style={{ opacity }}
                    >
                      {hasData ? (
                        <span className={`text-[10px] font-mono font-semibold ${textColor}`}>
                          {(winRate * 100).toFixed(0)}%
                        </span>
                      ) : (
                        <span className="text-[9px] text-gray-700">—</span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3 text-[10px] text-gray-500">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-red-500/40" />
          <span>&lt;40% win</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-yellow-500/30" />
          <span>40–60%</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-[#00d97e]/40" />
          <span>&gt;60% win</span>
        </div>
        <span className="ml-auto">min 3 trades to display</span>
      </div>

      {/* Fixed-position tooltip rendered via portal-like approach */}
      {tooltip.visible && tooltip.content && (
        <div
          className="fixed z-50 pointer-events-none"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            transform: 'translate(-50%, -100%)',
          }}
        >
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-2.5 shadow-xl text-xs whitespace-nowrap">
            <div className="font-semibold text-gray-200 mb-1">
              {tooltip.content.row} / {tooltip.content.col}
            </div>
            <div className="space-y-0.5 text-gray-400">
              <div>
                Win Rate:{' '}
                <span
                  className={
                    tooltip.content.winRate > 0.6
                      ? 'text-[#00d97e]'
                      : tooltip.content.winRate < 0.4
                        ? 'text-red-400'
                        : 'text-yellow-400'
                  }
                >
                  {(tooltip.content.winRate * 100).toFixed(1)}%
                </span>
              </div>
              <div>
                Trades:{' '}
                <span className="text-gray-300 font-mono">{tooltip.content.total}</span>
              </div>
              <div>
                Net P&amp;L:{' '}
                <span
                  className={
                    tooltip.content.profit >= 0 ? 'text-[#00d97e] font-mono' : 'text-red-400 font-mono'
                  }
                >
                  {tooltip.content.profit >= 0 ? '+' : ''}$
                  {tooltip.content.profit.toFixed(2)}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
