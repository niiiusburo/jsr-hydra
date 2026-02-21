'use client'

interface Badge {
  id: string
  name: string
  description: string
  icon: string
  earned_at: string
}

interface StrategyBadgesProps {
  badges: Badge[]
  compact?: boolean
}

const BADGE_ICONS: Record<string, string> = {
  sword: '\u2694\uFE0F',
  coins: '\uD83E\uDE99',
  fire: '\uD83D\uDD25',
  shield: '\uD83D\uDEE1\uFE0F',
  zap: '\u26A1',
  lock: '\uD83D\uDD12',
  trophy: '\uD83C\uDFC6',
  star: '\u2B50',
  gem: '\uD83D\uDC8E',
  globe: '\uD83C\uDF0D',
}

const BADGE_COLORS: Record<string, string> = {
  first_blood: '#EF4444',
  gold_rush: '#F59E0B',
  streak_master: '#F97316',
  survivor: '#10B981',
  speed_demon: '#3B82F6',
  risk_manager: '#8B5CF6',
  century: '#EC4899',
  ten_streak: '#FFD700',
  big_winner: '#14B8A6',
  multi_symbol: '#6366F1',
}

// All possible badges for showing locked state
const ALL_BADGE_IDS = [
  'first_blood', 'gold_rush', 'streak_master', 'survivor',
  'speed_demon', 'risk_manager', 'century', 'ten_streak',
  'big_winner', 'multi_symbol',
]

const BADGE_NAMES: Record<string, string> = {
  first_blood: 'First Blood',
  gold_rush: 'Gold Rush',
  streak_master: 'Streak Master',
  survivor: 'Survivor',
  speed_demon: 'Speed Demon',
  risk_manager: 'Risk Manager',
  century: 'Century',
  ten_streak: 'Unstoppable',
  big_winner: 'Big Winner',
  multi_symbol: 'Diversifier',
}

const BADGE_DESCRIPTIONS: Record<string, string> = {
  first_blood: 'Completed first trade',
  gold_rush: 'First trade on XAUUSD',
  streak_master: 'Achieved 5+ win streak',
  survivor: 'Recovered from 3+ loss streak',
  speed_demon: 'Profitable scalp under 5 minutes',
  risk_manager: '100 trades with stop-loss',
  century: 'Completed 100 trades',
  ten_streak: '10-win streak',
  big_winner: 'Single trade profit > 2R',
  multi_symbol: 'Traded on 4+ symbols',
}

const BADGE_ICON_MAP: Record<string, string> = {
  first_blood: 'sword',
  gold_rush: 'coins',
  streak_master: 'fire',
  survivor: 'shield',
  speed_demon: 'zap',
  risk_manager: 'lock',
  century: 'trophy',
  ten_streak: 'star',
  big_winner: 'gem',
  multi_symbol: 'globe',
}

export function StrategyBadges({ badges, compact = false }: StrategyBadgesProps) {
  const earnedIds = new Set(badges.map(b => b.id))

  if (compact) {
    // Only show earned badges in compact mode
    if (badges.length === 0) {
      return (
        <div className="text-xs text-gray-500 italic">No badges yet</div>
      )
    }

    return (
      <div className="flex flex-wrap gap-1.5">
        {badges.map(badge => {
          const color = BADGE_COLORS[badge.id] || '#6B7280'
          const iconKey = badge.icon || BADGE_ICON_MAP[badge.id] || 'star'
          const icon = BADGE_ICONS[iconKey] || ''

          return (
            <div
              key={badge.id}
              className="group relative flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium cursor-default"
              style={{
                backgroundColor: `${color}15`,
                border: `1px solid ${color}30`,
                color: color,
              }}
              title={`${badge.name}: ${badge.description}`}
            >
              <span className="text-sm">{icon}</span>
              <span>{badge.name}</span>
            </div>
          )
        })}
      </div>
    )
  }

  // Full view: show all badges, locked ones are grayed out
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-gray-300">Badges & Achievements</h4>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
        {ALL_BADGE_IDS.map(badgeId => {
          const isEarned = earnedIds.has(badgeId)
          const badge = badges.find(b => b.id === badgeId)
          const color = isEarned ? (BADGE_COLORS[badgeId] || '#6B7280') : '#374151'
          const iconKey = BADGE_ICON_MAP[badgeId] || 'star'
          const icon = BADGE_ICONS[iconKey] || ''
          const name = badge?.name || BADGE_NAMES[badgeId] || badgeId
          const description = badge?.description || BADGE_DESCRIPTIONS[badgeId] || ''

          return (
            <div
              key={badgeId}
              className={`flex flex-col items-center p-3 rounded-lg border transition-all ${
                isEarned
                  ? 'border-opacity-30'
                  : 'border-gray-700 opacity-30'
              }`}
              style={isEarned ? {
                backgroundColor: `${color}10`,
                borderColor: `${color}30`,
              } : {}}
            >
              <div
                className="text-2xl mb-1.5"
                style={isEarned ? { filter: 'none' } : { filter: 'grayscale(100%)' }}
              >
                {icon}
              </div>
              <span
                className="text-xs font-semibold text-center"
                style={{ color: isEarned ? color : '#6B7280' }}
              >
                {name}
              </span>
              <span className="text-[10px] text-gray-500 text-center mt-0.5">
                {description}
              </span>
              {isEarned && badge?.earned_at && (
                <span className="text-[9px] text-gray-600 mt-1">
                  {new Date(badge.earned_at).toLocaleDateString()}
                </span>
              )}
              {!isEarned && (
                <span className="text-[9px] text-gray-600 mt-1">Locked</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
