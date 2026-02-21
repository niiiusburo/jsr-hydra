'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { Lightbulb, ChevronLeft, ChevronRight } from 'lucide-react'

interface TipsProps {
  insights: string[]
}

export function LearningTips({ insights }: TipsProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [visible, setVisible] = useState(true)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const totalTips = insights.length

  const goTo = useCallback(
    (index: number) => {
      if (totalTips === 0) return
      setVisible(false)
      setTimeout(() => {
        setCurrentIndex(((index % totalTips) + totalTips) % totalTips)
        setVisible(true)
      }, 200)
    },
    [totalTips],
  )

  const next = useCallback(() => {
    goTo(currentIndex + 1)
  }, [currentIndex, goTo])

  const prev = useCallback(() => {
    goTo(currentIndex - 1)
  }, [currentIndex, goTo])

  // Auto-rotate every 15 seconds
  useEffect(() => {
    if (totalTips <= 1) return
    timerRef.current = setTimeout(() => {
      next()
    }, 15000)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [currentIndex, next, totalTips])

  const isEmpty = totalTips === 0

  return (
    <div className="bg-[#0a0a0a] border border-[#00d97e]/20 rounded-lg p-4">
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className="shrink-0 mt-0.5 p-1.5 rounded-md bg-[#00d97e]/10 border border-[#00d97e]/20">
          <Lightbulb size={14} className="text-[#00d97e]" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[#00d97e]/70">
              Brain Insight
            </span>
            {!isEmpty && (
              <span className="text-[10px] text-gray-600 font-mono">
                {currentIndex + 1} / {totalTips}
              </span>
            )}
          </div>

          {/* Tip text with fade transition */}
          <div
            className="transition-opacity duration-200"
            style={{ opacity: visible ? 1 : 0 }}
          >
            {isEmpty ? (
              <p className="text-sm text-gray-500 italic">
                No insights yet — the brain is still learning.
              </p>
            ) : (
              <p className="text-sm text-gray-300 leading-relaxed">
                {insights[currentIndex]}
              </p>
            )}
          </div>
        </div>

        {/* Navigation arrows */}
        {!isEmpty && totalTips > 1 && (
          <div className="shrink-0 flex items-center gap-1 mt-0.5">
            <button
              onClick={prev}
              aria-label="Previous insight"
              className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={next}
              aria-label="Next insight"
              className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>

      {/* Dot indicators */}
      {!isEmpty && totalTips > 1 && (
        <div className="flex justify-center gap-1 mt-3">
          {insights.map((_, i) => (
            <button
              key={i}
              onClick={() => goTo(i)}
              aria-label={`Go to insight ${i + 1}`}
              className={`w-1.5 h-1.5 rounded-full transition-all duration-200 ${
                i === currentIndex
                  ? 'bg-[#00d97e] w-3'
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
