'use client'

import React from 'react'

interface CardProps {
  title?: string
  children: React.ReactNode
  footer?: React.ReactNode
  className?: string
}

export function Card({
  title,
  children,
  footer,
  className = '',
}: CardProps) {
  return (
    <div className={`bg-brand-panel border border-gray-700 rounded-lg overflow-hidden transition-all duration-200 hover:border-gray-600 ${className}`}>
      {title && (
        <div className="px-6 py-4 border-b border-gray-700">
          <h3 className="text-lg font-semibold text-gray-100">{title}</h3>
        </div>
      )}
      <div className="px-6 py-4">
        {children}
      </div>
      {footer && (
        <div className="px-6 py-3 border-t border-gray-700 bg-black/20">
          {footer}
        </div>
      )}
    </div>
  )
}
