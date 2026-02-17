'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  TrendingUp,
  ArrowLeftRight,
  Shield,
  Settings,
  Menu,
  X,
} from 'lucide-react'

const navItems = [
  { href: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { href: '/dashboard/strategies', icon: TrendingUp, label: 'Strategies' },
  { href: '/dashboard/trades', icon: ArrowLeftRight, label: 'Trades' },
  { href: '/dashboard/risk', icon: Shield, label: 'Risk' },
  { href: '/dashboard/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
  const [isOpen, setIsOpen] = useState(false)
  const pathname = usePathname()

  const toggleSidebar = () => {
    setIsOpen(!isOpen)
  }

  const isActive = (href: string) => {
    if (href === '/dashboard' && pathname === '/dashboard') return true
    return pathname.startsWith(href) && href !== '/dashboard'
  }

  return (
    <>
      {/* Mobile Toggle Button */}
      <button
        onClick={toggleSidebar}
        className="fixed top-4 left-4 z-50 md:hidden p-2 rounded-lg bg-brand-panel border border-gray-700 text-gray-100"
      >
        {isOpen ? <X size={24} /> : <Menu size={24} />}
      </button>

      {/* Mobile Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed left-0 top-0 z-40 h-screen w-64 bg-brand-panel border-r border-gray-700 p-6 transition-transform duration-300 md:static md:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo */}
        <div className="mb-8 flex items-center gap-2">
          <div className="h-8 w-8 rounded bg-brand-accent-green flex items-center justify-center">
            <span className="text-brand-dark font-bold text-sm">H</span>
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-bold text-brand-accent-green">
              JSR
            </span>
            <span className="text-xs text-gray-400">HYDRA</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon
            const active = isActive(item.href)

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setIsOpen(false)}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 ${
                  active
                    ? 'bg-gray-700 text-brand-accent-green'
                    : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800'
                }`}
              >
                <Icon size={20} />
                <span className="font-medium">{item.label}</span>
              </Link>
            )
          })}
        </nav>

        {/* Footer */}
        <div className="absolute bottom-6 left-6 right-6">
          <div className="text-xs text-gray-500 text-center">
            <p>JSR Hydra v1.0.0</p>
          </div>
        </div>
      </aside>
    </>
  )
}
