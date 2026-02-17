'use client'

import React from 'react'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'

interface RegimeData {
  state: 'TRENDING_UP' | 'TRENDING_DOWN' | 'RANGING' | 'VOLATILE'
  confidence: number
  conviction: number
  lastDetected: string
}

interface RegimeCardProps {
  data?: RegimeData
  loading?: boolean
}

const mockData: RegimeData = {
  state: 'TRENDING_UP',
  confidence: 0.85,
  conviction: 8,
  lastDetected: '2026-02-16 14:30:00',
}

export function RegimeCard({ data = mockData, loading = false }: RegimeCardProps) {
  if (loading) {
    return (
      <Card title="Market Regime">
        <div className="space-y-4">
          <div className="h-4 bg-gray-700/50 rounded animate-pulse w-2/3" />
          <div className="h-4 bg-gray-700/50 rounded animate-pulse w-1/2" />
        </div>
      </Card>
    )
  }

  const regimeConfig = {
    TRENDING_UP: { label: 'Trending Up', variant: 'success' as const },
    TRENDING_DOWN: { label: 'Trending Down', variant: 'danger' as const },
    RANGING: { label: 'Ranging', variant: 'warning' as const },
    VOLATILE: { label: 'Volatile', variant: 'info' as const },
  }

  const regime = regimeConfig[data.state]
  const confidencePercent = (data.confidence * 100).toFixed(0)

  return (
    <Card title="Market Regime">
      <div className="space-y-6">
        {/* Current Regime */}
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">Current State</p>
          <Badge variant={regime.variant}>{regime.label}</Badge>
        </div>

        {/* Confidence Score */}
        <div>
          <div className="flex justify-between mb-2">
            <p className="text-sm text-gray-300">Confidence Score</p>
            <p className="text-sm font-semibold text-brand-accent-green">{confidencePercent}%</p>
          </div>
          <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-brand-accent-green"
              style={{ width: `${data.confidence * 100}%` }}
            />
          </div>
        </div>

        {/* Conviction Score */}
        <div>
          <p className="text-sm text-gray-300 mb-2">Conviction Score</p>
          <div className="flex items-center gap-2">
            <p className="text-2xl font-bold text-brand-accent-green">{data.conviction}/10</p>
            <div className="flex gap-1">
              {Array.from({ length: 10 }).map((_, i) => (
                <div
                  key={i}
                  className={`w-1.5 h-6 rounded-sm ${
                    i < data.conviction
                      ? 'bg-brand-accent-green'
                      : 'bg-gray-700'
                  }`}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Last Detected */}
        <div className="border-t border-gray-700 pt-4">
          <p className="text-xs text-gray-400">Last Detected</p>
          <p className="text-sm text-gray-300 mt-1">{data.lastDetected}</p>
        </div>
      </div>
    </Card>
  )
}
