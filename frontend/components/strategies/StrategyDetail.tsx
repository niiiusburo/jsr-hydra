'use client'

import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'

interface StrategyDetailProps {
  code: string
  name: string
  status: 'active' | 'paused' | 'stopped'
  allocation: number
  description: string
  winRate: number
  profitFactor: number
  totalTrades: number
  totalProfit: number
  performanceData: Array<{ date: string; profit: number }>
  config: Record<string, any>
  onStatusChange?: (code: string, status: 'active' | 'paused' | 'stopped') => void
}

export function StrategyDetail({
  code,
  name,
  status,
  allocation,
  description,
  winRate,
  profitFactor,
  totalTrades,
  totalProfit,
  performanceData,
  config,
  onStatusChange,
}: StrategyDetailProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'performance' | 'config'>('overview')
  const [isToggling, setIsToggling] = useState(false)

  const handleToggleStatus = async () => {
    const newStatus = status === 'active' ? 'paused' : 'active'
    setIsToggling(true)
    try {
      const response = await fetch(`/api/strategies/${code}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
      if (response.ok) {
        onStatusChange?.(code, newStatus)
      }
    } catch (error) {
      console.error('Failed to toggle strategy status:', error)
    } finally {
      setIsToggling(false)
    }
  }

  const statusVariant = {
    active: 'success' as const,
    paused: 'warning' as const,
    stopped: 'danger' as const,
  }[status]

  const statusLabel = {
    active: 'Active',
    paused: 'Paused',
    stopped: 'Stopped',
  }[status]

  return (
    <Card className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-gray-700 pb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-100">{name}</h2>
          <p className="text-sm text-gray-400 mt-1">{description}</p>
        </div>
        <div className="flex items-center gap-4">
          <Badge variant={statusVariant}>{statusLabel}</Badge>
          <button
            onClick={handleToggleStatus}
            disabled={isToggling}
            className={`px-4 py-2 rounded-lg font-semibold transition-all ${
              status === 'active'
                ? 'btn-danger'
                : 'bg-green-600 text-white hover:bg-green-700'
            } disabled:opacity-50`}
          >
            {isToggling ? 'Updating...' : status === 'active' ? 'Pause' : 'Activate'}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-gray-700">
        {(['overview', 'performance', 'config'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-3 font-medium transition-all border-b-2 ${
              activeTab === tab
                ? 'text-brand-accent-green border-brand-accent-green'
                : 'text-gray-400 border-transparent hover:text-gray-300'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div>
        {activeTab === 'overview' && (
          <div className="grid md:grid-cols-2 gap-6">
            {/* Basic Info */}
            <div className="space-y-4">
              <div>
                <span className="text-sm text-gray-400">Strategy Code</span>
                <p className="text-lg font-mono text-gray-100">{code}</p>
              </div>
              <div>
                <span className="text-sm text-gray-400">Allocation</span>
                <p className="text-lg font-bold text-brand-accent-green">{allocation}%</p>
              </div>
              <div>
                <span className="text-sm text-gray-400">Status</span>
                <p className="text-lg font-semibold">{statusLabel}</p>
              </div>
            </div>

            {/* Metrics */}
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-black/20 p-3 rounded-lg border border-gray-700">
                  <span className="text-xs text-gray-400">Win Rate</span>
                  <p className="text-lg font-bold text-brand-accent-green">{(winRate * 100).toFixed(1)}%</p>
                </div>
                <div className="bg-black/20 p-3 rounded-lg border border-gray-700">
                  <span className="text-xs text-gray-400">Profit Factor</span>
                  <p className="text-lg font-bold text-blue-400">{profitFactor.toFixed(2)}</p>
                </div>
                <div className="bg-black/20 p-3 rounded-lg border border-gray-700">
                  <span className="text-xs text-gray-400">Total Trades</span>
                  <p className="text-lg font-bold text-gray-100">{totalTrades}</p>
                </div>
                <div className={`bg-black/20 p-3 rounded-lg border border-gray-700`}>
                  <span className="text-xs text-gray-400">Total Profit</span>
                  <p className={`text-lg font-bold ${totalProfit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${totalProfit.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'performance' && (
          <div className="space-y-6">
            <div className="h-96 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={performanceData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="date" stroke="#9ca3af" />
                  <YAxis stroke="#9ca3af" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#111827',
                      border: '1px solid #374151',
                      borderRadius: '8px',
                    }}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="profit"
                    stroke="#00d97e"
                    dot={false}
                    strokeWidth={2}
                    name="Cumulative Profit"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="text-sm text-gray-400">
              30-day performance history
            </div>
          </div>
        )}

        {activeTab === 'config' && (
          <div className="space-y-4">
            <div className="bg-black/30 p-4 rounded-lg border border-gray-700 font-mono text-sm text-gray-300 overflow-x-auto">
              <pre>{JSON.stringify(config, null, 2)}</pre>
            </div>
            <p className="text-sm text-gray-400">
              Configuration is read-only. Modify settings through the settings page.
            </p>
          </div>
        )}
      </div>
    </Card>
  )
}
