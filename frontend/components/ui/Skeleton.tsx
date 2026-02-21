'use client'

import React from 'react'

interface SkeletonProps {
  variant: 'text' | 'card' | 'chart'
  className?: string
}

export function Skeleton({ variant, className = '' }: SkeletonProps) {
  const baseClasses = 'bg-gray-700/50 animate-pulse rounded'

  const variantStyles = {
    text: `${baseClasses} h-4 w-full`,
    card: `${baseClasses} h-48 w-full`,
    chart: `${baseClasses} h-64 w-full`,
  }

  return <div className={`${variantStyles[variant]} ${className}`} />
}

export function SkeletonGrid() {
  return (
    <div className="space-y-6">
      {/* Top Row: Account (2/3) + Regime (1/3) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
        <div className="lg:col-span-2">
          <Skeleton variant="card" className="h-64" />
        </div>
        <Skeleton variant="card" className="h-64" />
      </div>

      {/* Equity Chart */}
      <Skeleton variant="chart" />

      {/* Strategies & System Status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        <Skeleton variant="card" />
        <Skeleton variant="card" />
      </div>

      {/* Recent Trades */}
      <Skeleton variant="card" className="h-56" />
    </div>
  )
}
