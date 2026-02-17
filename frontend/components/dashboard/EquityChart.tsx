'use client'

import React from 'react'
import { LineChart, Line, Area, AreaChart, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { Card } from '@/components/ui/Card'

interface EquityPoint {
  timestamp: string
  value: number
}

interface EquityChartProps {
  data?: EquityPoint[]
  loading?: boolean
}

const mockData: EquityPoint[] = [
  { timestamp: '2026-01-20', value: 100000 },
  { timestamp: '2026-01-21', value: 100500 },
  { timestamp: '2026-01-22', value: 100200 },
  { timestamp: '2026-01-23', value: 101000 },
  { timestamp: '2026-01-24', value: 101500 },
  { timestamp: '2026-01-25', value: 101200 },
  { timestamp: '2026-01-26', value: 102000 },
  { timestamp: '2026-01-27', value: 101800 },
  { timestamp: '2026-01-28', value: 102500 },
  { timestamp: '2026-01-29', value: 102300 },
  { timestamp: '2026-01-30', value: 103000 },
  { timestamp: '2026-01-31', value: 102800 },
  { timestamp: '2026-02-01', value: 103500 },
  { timestamp: '2026-02-02', value: 104000 },
  { timestamp: '2026-02-03', value: 103700 },
  { timestamp: '2026-02-04', value: 104500 },
  { timestamp: '2026-02-05', value: 104200 },
  { timestamp: '2026-02-06', value: 105000 },
  { timestamp: '2026-02-07', value: 104800 },
  { timestamp: '2026-02-08', value: 105500 },
  { timestamp: '2026-02-09', value: 105800 },
  { timestamp: '2026-02-10', value: 106000 },
  { timestamp: '2026-02-11', value: 105700 },
  { timestamp: '2026-02-12', value: 106500 },
  { timestamp: '2026-02-13', value: 106800 },
  { timestamp: '2026-02-14', value: 107000 },
  { timestamp: '2026-02-15', value: 107500 },
  { timestamp: '2026-02-16', value: 107800 },
]

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

export function EquityChart({ data = mockData, loading = false }: EquityChartProps) {
  if (loading) {
    return (
      <Card title="Equity Curve (30 Days)">
        <div className="h-64 bg-gray-700/50 rounded animate-pulse" />
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
            domain="dataMin"
            tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
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
