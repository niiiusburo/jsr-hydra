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
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} variant="card" />
      ))}
    </div>
  )
}
