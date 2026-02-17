'use client'

import React from 'react'
import { Card } from '@/components/ui/Card'

interface Service {
  name: string
  status: 'up' | 'down' | 'degraded'
}

interface SystemStatusData {
  services: Service[]
  uptime: number
  version: string
}

interface SystemStatusProps {
  data?: SystemStatusData
  loading?: boolean
}

const mockData: SystemStatusData = {
  services: [
    { name: 'MT5', status: 'up' },
    { name: 'PostgreSQL', status: 'up' },
    { name: 'Redis', status: 'up' },
    { name: 'Engine', status: 'up' },
  ],
  uptime: 86400 * 15,
  version: '1.0.0',
}

const statusConfig = {
  up: { color: 'bg-brand-accent-green', label: 'Up' },
  down: { color: 'bg-brand-accent-red', label: 'Down' },
  degraded: { color: 'bg-yellow-500', label: 'Degraded' },
}

export function SystemStatus({ data = mockData, loading = false }: SystemStatusProps) {
  if (loading) {
    return (
      <Card title="System Status">
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-8 bg-gray-700/50 rounded animate-pulse" />
          ))}
        </div>
      </Card>
    )
  }

  const days = Math.floor(data.uptime / (86400))
  const hours = Math.floor((data.uptime % 86400) / 3600)
  const minutes = Math.floor((data.uptime % 3600) / 60)

  return (
    <Card title="System Status">
      <div className="space-y-4">
        {/* Services */}
        {data.services.map((service) => {
          const config = statusConfig[service.status]
          return (
            <div key={service.name} className="flex items-center justify-between p-3 bg-black/20 rounded-lg border border-gray-700">
              <span className="text-gray-200 font-medium">{service.name}</span>
              <div className="flex items-center gap-2">
                <div className={`w-2.5 h-2.5 rounded-full ${config.color}`} />
                <span className="text-xs text-gray-400">{config.label}</span>
              </div>
            </div>
          )
        })}

        <div className="border-t border-gray-700 pt-4 mt-4">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-gray-400 text-xs">Uptime</p>
              <p className="text-gray-100 font-semibold mt-1">
                {days}d {hours}h {minutes}m
              </p>
            </div>
            <div>
              <p className="text-gray-400 text-xs">Version</p>
              <p className="text-gray-100 font-semibold mt-1">{data.version}</p>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}
