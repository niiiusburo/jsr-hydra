'use client'

import { useState, useEffect } from 'react'
import { StrategyDetail } from '@/components/strategies/StrategyDetail'
import { AllocationManager } from '@/components/strategies/AllocationManager'
import { Card } from '@/components/ui/Card'

interface Strategy {
  code: string
  name: string
  description: string
  status: 'active' | 'paused' | 'stopped'
  allocation: number
  winRate: number
  profitFactor: number
  totalTrades: number
  totalProfit: number
  performanceData: Array<{ date: string; profit: number }>
  config: Record<string, any>
}

// Mock data generator
const generateMockStrategies = (): Strategy[] => {
  const today = new Date()
  const generatePerformanceData = () => {
    return Array.from({ length: 30 }, (_, i) => {
      const date = new Date(today)
      date.setDate(date.getDate() - (29 - i))
      return {
        date: date.toISOString().split('T')[0],
        profit: Math.random() * 10000 - 3000 + i * 150,
      }
    })
  }

  return [
    {
      code: 'STRATEGY_A',
      name: 'Mean Reversion Strategy',
      description: 'Trades based on statistical mean reversion signals using Bollinger Bands',
      status: 'active',
      allocation: 25,
      winRate: 0.58,
      profitFactor: 1.8,
      totalTrades: 145,
      totalProfit: 12500.50,
      performanceData: generatePerformanceData(),
      config: {
        period: 20,
        stdDev: 2,
        maxPosition: 5,
        stopLoss: 100,
        takeProfit: 150,
      },
    },
    {
      code: 'STRATEGY_B',
      name: 'Trend Following Strategy',
      description: 'Momentum-based strategy using moving average crossovers',
      status: 'active',
      allocation: 25,
      winRate: 0.52,
      profitFactor: 1.5,
      totalTrades: 89,
      totalProfit: 8750.25,
      performanceData: generatePerformanceData(),
      config: {
        fastMA: 12,
        slowMA: 26,
        rsiThreshold: 30,
        maxPosition: 3,
        stopLoss: 80,
      },
    },
    {
      code: 'STRATEGY_C',
      name: 'Machine Learning Classifier',
      description: 'Neural network-based pattern recognition and prediction',
      status: 'paused',
      allocation: 25,
      winRate: 0.61,
      profitFactor: 2.1,
      totalTrades: 67,
      totalProfit: 15200.75,
      performanceData: generatePerformanceData(),
      config: {
        modelVersion: '2.1.0',
        confidence_threshold: 0.72,
        lookback_period: 50,
        batch_size: 32,
      },
    },
    {
      code: 'STRATEGY_D',
      name: 'Market Microstructure',
      description: 'Order flow analysis and liquidity detection strategy',
      status: 'stopped',
      allocation: 25,
      winRate: 0.55,
      profitFactor: 1.6,
      totalTrades: 203,
      totalProfit: 9800.00,
      performanceData: generatePerformanceData(),
      config: {
        orderFlowThreshold: 0.65,
        liquidityPeriod: 5,
        spreadLimit: 2,
        maxSpread: 5,
      },
    },
  ]
}

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [expandedStrategy, setExpandedStrategy] = useState<string | null>(null)

  useEffect(() => {
    // Simulate API call
    setTimeout(() => {
      setStrategies(generateMockStrategies())
      setIsLoading(false)
    }, 300)
  }, [])

  const handleStatusChange = (code: string, status: 'active' | 'paused' | 'stopped') => {
    setStrategies(strategies.map(s =>
      s.code === code ? { ...s, status } : s
    ))
  }

  const handleAllocationSave = (allocations: Record<string, number>) => {
    setStrategies(strategies.map(s => ({
      ...s,
      allocation: allocations[s.code] || s.allocation,
    })))
  }

  const totalAllocation = strategies.reduce((sum, s) => sum + s.allocation, 0)
  const activeCount = strategies.filter(s => s.status === 'active').length
  const totalWinRate = strategies.length > 0
    ? strategies.reduce((sum, s) => sum + s.winRate, 0) / strategies.length
    : 0
  const totalProfit = strategies.reduce((sum, s) => sum + s.totalProfit, 0)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-gray-400">Loading strategies...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-100">Strategies</h1>
        <p className="text-gray-400 mt-2">Manage and monitor your trading strategies</p>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="text-sm text-gray-400">Active Strategies</div>
          <div className="text-2xl font-bold text-brand-accent-green mt-2">{activeCount}/4</div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-gray-400">Total Allocation</div>
          <div className={`text-2xl font-bold mt-2 ${totalAllocation <= 100 ? 'text-brand-accent-green' : 'text-brand-accent-red'}`}>
            {totalAllocation}%
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-gray-400">Avg Win Rate</div>
          <div className="text-2xl font-bold text-blue-400 mt-2">{(totalWinRate * 100).toFixed(1)}%</div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-gray-400">Total Profit (30d)</div>
          <div className={`text-2xl font-bold mt-2 ${totalProfit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${totalProfit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </Card>
      </div>

      {/* Strategy Cards */}
      <div className="grid gap-4">
        {strategies.map(strategy => (
          <div key={strategy.code}>
            <button
              onClick={() => setExpandedStrategy(expandedStrategy === strategy.code ? null : strategy.code)}
              className="w-full text-left"
            >
              <Card className="p-6 hover:border-gray-600 cursor-pointer transition-all">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-lg font-bold text-gray-100">{strategy.name}</h3>
                    <p className="text-sm text-gray-400 mt-1">{strategy.description}</p>
                    <div className="flex flex-wrap gap-4 mt-4">
                      <div>
                        <span className="text-xs text-gray-500">Status</span>
                        <p className="text-sm font-semibold mt-1 capitalize">
                          {strategy.status === 'active' && <span className="text-green-400">● Active</span>}
                          {strategy.status === 'paused' && <span className="text-yellow-400">● Paused</span>}
                          {strategy.status === 'stopped' && <span className="text-red-400">● Stopped</span>}
                        </p>
                      </div>
                      <div>
                        <span className="text-xs text-gray-500">Allocation</span>
                        <p className="text-sm font-semibold text-brand-accent-green mt-1">{strategy.allocation}%</p>
                      </div>
                      <div>
                        <span className="text-xs text-gray-500">Win Rate</span>
                        <p className="text-sm font-semibold text-blue-400 mt-1">{(strategy.winRate * 100).toFixed(1)}%</p>
                      </div>
                      <div>
                        <span className="text-xs text-gray-500">Profit Factor</span>
                        <p className="text-sm font-semibold text-purple-400 mt-1">{strategy.profitFactor.toFixed(2)}</p>
                      </div>
                      <div>
                        <span className="text-xs text-gray-500">Trades</span>
                        <p className="text-sm font-semibold text-gray-300 mt-1">{strategy.totalTrades}</p>
                      </div>
                    </div>
                  </div>
                  <div className="text-right ml-4">
                    <div className="text-xs text-gray-500">30d Profit</div>
                    <p className={`text-xl font-bold mt-1 ${strategy.totalProfit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${strategy.totalProfit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                  </div>
                </div>
              </Card>
            </button>

            {/* Expanded Detail */}
            {expandedStrategy === strategy.code && (
              <div className="mt-4">
                <StrategyDetail
                  {...strategy}
                  onStatusChange={handleStatusChange}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Allocation Manager */}
      <AllocationManager onSave={handleAllocationSave} />
    </div>
  )
}
