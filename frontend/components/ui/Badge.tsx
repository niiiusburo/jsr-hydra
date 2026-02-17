'use client'

import React from 'react'

interface BadgeProps {
  variant: 'success' | 'warning' | 'danger' | 'info'
  children: React.ReactNode
  dot?: boolean
  className?: string
}

export function Badge({
  variant,
  children,
  dot = true,
  className = '',
}: BadgeProps) {
  const variantStyles = {
    success: 'bg-green-900/30 text-green-400 border border-green-700/50',
    warning: 'bg-yellow-900/30 text-yellow-400 border border-yellow-700/50',
    danger: 'bg-red-900/30 text-red-400 border border-red-700/50',
    info: 'bg-blue-900/30 text-blue-400 border border-blue-700/50',
  }

  const dotColors = {
    success: 'bg-green-500',
    warning: 'bg-yellow-500',
    danger: 'bg-red-500',
    info: 'bg-blue-500',
  }

  return (
    <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium ${variantStyles[variant]} ${className}`}>
      {dot && <span className={`w-2 h-2 rounded-full ${dotColors[variant]}`} />}
      {children}
    </span>
  )
}
