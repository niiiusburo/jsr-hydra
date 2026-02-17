'use client'

import { useState } from 'react'
import { Power } from 'lucide-react'

interface ConnectionStatus {
  name: string
  connected: boolean
}

export default function Header() {
  const [isSystemRunning, setIsSystemRunning] = useState(true)
  const [accountEquity, setAccountEquity] = useState(50000.00)

  const connectionStatuses: ConnectionStatus[] = [
    { name: 'MT5', connected: true },
    { name: 'Redis', connected: true },
    { name: 'DB', connected: true },
  ]

  const handleKillSwitch = () => {
    if (confirm('Are you sure you want to stop the trading system?')) {
      setIsSystemRunning(false)
      // TODO: Implement kill switch API call
    }
  }

  return (
    <header className="sticky top-0 z-30 border-b border-gray-700 bg-brand-panel">
      <div className="px-6 py-4 flex items-center justify-between">
        {/* Left Section - Status Indicator */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div
              className={`status-indicator ${
                isSystemRunning ? 'status-active' : 'status-inactive'
              }`}
            />
            <span className="text-sm font-medium">
              {isSystemRunning ? 'System Running' : 'System Stopped'}
            </span>
          </div>

          {/* Connection Status */}
          <div className="hidden md:flex items-center gap-4 ml-6 pl-6 border-l border-gray-700">
            {connectionStatuses.map((status) => (
              <div key={status.name} className="flex items-center gap-2">
                <div
                  className={`status-indicator ${
                    status.connected ? 'status-active' : 'status-error'
                  }`}
                />
                <span className="text-xs text-gray-400">{status.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Center Section - Equity Display */}
        <div className="flex flex-col items-center">
          <span className="text-xs text-gray-400">Account Equity</span>
          <span className="text-lg font-bold text-brand-accent-green">
            ${accountEquity.toLocaleString('en-US', {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>

        {/* Right Section - Kill Switch */}
        <button
          onClick={handleKillSwitch}
          disabled={!isSystemRunning}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-semibold transition-all duration-200 ${
            isSystemRunning
              ? 'btn-danger'
              : 'opacity-50 cursor-not-allowed bg-gray-700 text-gray-400'
          }`}
        >
          <Power size={18} />
          <span className="text-sm">Kill Switch</span>
        </button>
      </div>
    </header>
  )
}
