'use client'

import React from 'react'

interface Factor {
  name: string
  contribution: number  // -1 to +1
  description: string
}

interface AttributionProps {
  factors: Factor[]
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

export function PerformanceAttribution({ factors }: AttributionProps) {
  if (factors.length === 0) {
    return (
      <div className="flex items-center justify-center h-24 text-gray-600 text-sm">
        No attribution data available yet.
      </div>
    )
  }

  // Sort by absolute contribution descending
  const sorted = [...factors].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  )

  // Max absolute value for bar scaling (min 0.1 to avoid all-zero stretching)
  const maxAbs = Math.max(0.1, ...sorted.map((f) => Math.abs(f.contribution)))

  return (
    <div className="space-y-2">
      {/* Zero-line header label */}
      <div className="flex items-center text-[10px] text-gray-600 mb-1">
        <div className="w-28 shrink-0" />
        <div className="flex-1 relative h-3">
          {/* Center line label */}
          <span className="absolute left-1/2 -translate-x-1/2 font-mono">0</span>
        </div>
        <div className="w-14 shrink-0" />
      </div>

      {sorted.map((factor) => {
        const isPositive = factor.contribution >= 0
        const absContrib = Math.abs(factor.contribution)
        // Fraction of the half-bar (0 → maxAbs → 50% of container)
        const barWidthPct = clamp((absContrib / maxAbs) * 50, 0, 50)

        return (
          <div key={factor.name} className="group flex items-center gap-2">
            {/* Factor name */}
            <div
              className="w-28 shrink-0 text-right text-[11px] text-gray-400 font-mono truncate"
              title={factor.description}
            >
              {factor.name}
            </div>

            {/* Bar container — split at center */}
            <div className="flex-1 flex items-center h-6 bg-gray-900 rounded overflow-hidden relative border border-gray-800">
              {/* Center divider */}
              <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gray-700 z-10" />

              {isPositive ? (
                // Positive bar: starts at center, grows right
                <>
                  <div className="flex-1" />
                  <div
                    className="h-full transition-all duration-500 rounded-r"
                    style={{
                      width: `${barWidthPct}%`,
                      backgroundColor: '#00d97e',
                      opacity: 0.7,
                    }}
                  />
                  <div style={{ width: `${50 - barWidthPct}%` }} />
                </>
              ) : (
                // Negative bar: starts at center, grows left
                <>
                  <div style={{ width: `${50 - barWidthPct}%` }} />
                  <div
                    className="h-full transition-all duration-500 rounded-l"
                    style={{
                      width: `${barWidthPct}%`,
                      backgroundColor: '#ef4444',
                      opacity: 0.7,
                    }}
                  />
                  <div className="flex-1" />
                </>
              )}
            </div>

            {/* Value */}
            <div
              className={`w-14 shrink-0 text-right text-[11px] font-mono font-semibold ${
                isPositive ? 'text-[#00d97e]' : 'text-red-400'
              }`}
            >
              {isPositive ? '+' : ''}
              {factor.contribution.toFixed(3)}
            </div>
          </div>
        )
      })}

      {/* Description tooltip area — show on hover via title attrs above */}
      <p className="text-[10px] text-gray-600 mt-2">
        Hover factor name for description. Bars scaled to largest absolute contributor.
      </p>
    </div>
  )
}
