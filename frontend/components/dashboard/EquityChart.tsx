'use client'

import React from 'react'
import { Area, AreaChart, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { Card } from '@/components/ui/Card'

interface EquityPoint {
  timestamp: string
  value: number
}

interface EquityChartProps {
  data?: EquityPoint[]
  loading?: boolean
}

const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload
    return (
      <div className="bg-brand-panel border border-gray-700 rounded p-3 shadow-lg">
        <p className="text-gray-300 text-sm">{data.timestamp}</p>
        <p className="text-brand-accent-green font-semibold">
          ${data.value.toLocaleString('en-US', { maximumFractionDigits: 0 })}
        </p>
      </div>
    )
  }
  return null
}

export function EquityChart({ data, loading = false }: EquityChartProps) {
  if (loading) {
    return (
      <Card title="Equity Curve (30 Days)">
        <div className="h-64 bg-gray-700/50 rounded animate-pulse" />
      </Card>
    )
  }

  if (!data || data.length === 0) {
    return (
      <Card title="Equity Curve (30 Days)">
        <div className="h-64 flex items-center justify-center">
          <p className="text-gray-400 text-sm">
            Equity curve data is not yet available. It will appear once the system records equity snapshots.
          </p>
        </div>
      </Card>
    )
  }

  return (
    <Card title="Equity Curve (30 Days)">
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#00d97e" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#00d97e" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="timestamp"
            tick={{ fill: '#9CA3AF', fontSize: 12 }}
            stroke="#4B5563"
            style={{ fontSize: '12px' }}
          />
          <YAxis
            tick={{ fill: '#9CA3AF', fontSize: 12 }}
            stroke="#4B5563"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(value) => value >= 1000 ? `$${(value / 1000).toFixed(0)}k` : `$${value.toFixed(0)}`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#00d97e"
            strokeWidth={2}
            fill="url(#equityGradient)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  )
}
