import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Chip, IconButton } from './ui'
import { Avatar3D, AvatarTile } from './Avatar3D'
import { useLang, useMoney, useT } from '../lib/i18n'
import type { Persona } from '../types'

const ICONS: Record<string, ReactNode> = {
  folder: <path d="M3 6a2 2 0 0 1 2-2h3.6l1.7 2H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  plus: <path d="M12 5v14M5 12h14" />,
  inbox: <path d="M4 13h4l1.5 3h5L16 13h4M4 13 6.5 5h11L20 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />,
  wrench: <path d="M14.7 6.3a4 4 0 0 0 5 5L21 10v9H5a2 2 0 0 1-2-2v-1l9.6-9.6z" />,
  check: <path d="m4 12.5 5 5L20 6.5" />,
  shield: <path d="M12 3l7.5 3v6c0 4.5-3 7.6-7.5 9-4.5-1.4-7.5-4.5-7.5-9V6z" />,
  'arrow-back': <path d="M9 15 4 10l5-5M4 10h9a7 7 0 0 1 0 14h-3" />,
  chart: <path d="M4 20V9m5 11V4m5 16v-7m5 7V7" />,
  lock: <path d="M6 11V8a6 6 0 0 1 12 0v3M5 11h14v9H5z" />,
  gauge: <path d="M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm2.5-3.5L19 6M4 18a9 9 0 1 1 16 0z" />,
}

function Icon({ name, className = '' }: { name: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round"
      className={`w-[18px] h-[18px] shrink-0 ${className}`} aria-hidden
    >
      {ICONS[name] ?? ICONS.folder}
    </svg>
  )
}

/** EN / DE, as a single segmented control. The whole platform follows it. */
function LanguageToggle() {
  const { lang, setLang } = useLang()
  const t = useT()
  return (
    <div
      className="flex items-center rounded-full bg-ink-100/80 p-[3px]"
      role="group"
      aria-label={t('shell.language')}
    >
      {(['en', 'de'] as const).map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={lang === code}
          className={`px-2.5 py-1 rounded-full text-[11.5px] font-medium uppercase tracking-wide transition-all ${
            lang === code
              ? 'bg-white text-az-700 shadow-[0_1px_3px_rgba(15,23,42,0.14)]'
              : 'text-ink-500 hover:text-ink-700'
          }`}
        >
          {code}
        </button>
      ))}
    </div>
  )
}

export function Shell({
  personas, active, onSwitch, feature, onFeature, children, onReset, resetting,
}: {
  personas: Persona[]
  active: Persona
  onSwitch: (key: string) => void
  feature: string
  onFeature: (key: string) => void
  children: ReactNode
  onReset: () => void
  resetting: boolean
}) {
  const t = useT()
  const money = useMoney()
  const [open, setOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const menu = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const away = (e: MouseEvent) => {
      if (menu.current && !menu.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  const current = active.features.find((f) => f.key === feature) ?? active.features[0]

  return (
    <div className="min-h-full flex bg-white">
      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <aside
        className={`shrink-0 flex flex-col sticky top-0 h-screen bg-white transition-[width] duration-200 ${
          collapsed ? 'w-[72px]' : 'w-[248px]'
        }`}
      >
        <div className="h-16 flex items-center gap-2 px-4">
          <IconButton
            title={collapsed ? t('shell.expand') : t('shell.collapse')}
            onClick={() => setCollapsed((c) => !c)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
                 strokeLinecap="round" className="w-5 h-5">
              <path d="M4 6h16M4 12h10M4 18h16" />
            </svg>
          </IconButton>
          {!collapsed && (
            <div className="flex items-center gap-2 min-w-0">
              <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden className="shrink-0">
                <rect width="24" height="24" rx="6" fill="#003781" />
                <path d="M6.5 17V9.9C6.5 8.6 7.5 7.5 8.9 7.5h6.2c1.4 0 2.4 1.1 2.4 2.4V17"
                      stroke="#fff" strokeWidth="1.9" fill="none" strokeLinecap="round" />
                <path d="M6.5 13.3h11" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" />
              </svg>
              <span className="text-[15px] text-ink-800 tracking-[-0.01em] truncate">
                {t('app.name')}
              </span>
            </div>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-2">
          {active.features.map((f) => {
            const on = f.key === feature
            const label = t(`nav.${f.key}`, f.label)
            return (
              <button
                key={f.key}
                type="button"
                title={collapsed ? label : t(`navhint.${f.key}`, f.hint)}
                onClick={() => onFeature(f.key)}
                className={`w-full flex items-center gap-3 rounded-full mb-1 transition-colors ${
                  collapsed ? 'justify-center py-2.5' : 'px-4 py-2.5'
                } ${on ? 'bg-air text-az-700 font-medium' : 'text-ink-700 hover:bg-ink-50'}`}
              >
                <Icon name={f.icon} />
                {!collapsed && (
                  <span className="text-[13.5px] truncate text-left">{label}</span>
                )}
              </button>
            )
          })}
        </nav>
      </aside>

      {/* ── Main ────────────────────────────────────────────────── */}
      <div className="flex-1 min-w-0 border-l border-ink-100 bg-ink-50/40">
        <header className="h-16 px-8 flex items-center justify-between bg-white border-b border-ink-100 sticky top-0 z-20">
          <div className="flex items-baseline gap-3 min-w-0">
            <span className="text-[15px] text-ink-900">
              {t(`nav.${current?.key}`, current?.label ?? '')}
            </span>
            <span className="text-[12.5px] text-ink-500 truncate hidden md:block">
              {t(`navhint.${current?.key}`, current?.hint ?? '')}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <LanguageToggle />

            <IconButton
              title={resetting ? t('shell.resetting') : t('shell.reset')}
              onClick={onReset}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
                   strokeLinecap="round" strokeLinejoin="round"
                   className={`w-[18px] h-[18px] ${resetting ? 'animate-spin' : ''}`}>
                <path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5" />
              </svg>
            </IconButton>

            {/* ── Role switcher: the role, and nothing about the person ── */}
            <div className="relative" ref={menu}>
              <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                aria-haspopup="menu"
                aria-expanded={open}
                className="flex items-center gap-2.5 pl-1.5 pr-3 py-1.5 rounded-full hover:bg-ink-50 transition-colors"
              >
                <AvatarTile avatar={active.avatar} accent={active.accent} size={34} />
                <span className="text-[13px] text-ink-900 hidden sm:block">
                  {t(`role.${active.key}`, active.role_label)}
                </span>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                     strokeLinecap="round" className="w-4 h-4 text-ink-500">
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </button>

              {open && (
                <div
                  role="menu"
                  className="absolute right-0 mt-2 w-[332px] bg-white rounded-2xl elev-3 overflow-hidden fade-up z-30 py-2"
                >
                  <div className="px-4 pb-2 text-[11.5px] text-ink-500 uppercase tracking-wide">
                    {t('shell.switchRole')}
                  </div>
                  {personas.map((p) => {
                    const on = p.key === active.key
                    return (
                      <button
                        key={p.key}
                        type="button"
                        role="menuitem"
                        onClick={() => { onSwitch(p.key); setOpen(false) }}
                        className={`w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors ${
                          on ? 'bg-air' : 'hover:bg-ink-50'
                        }`}
                      >
                        <Avatar3D avatar={p.avatar} accent={p.accent} size={38} />
                        <span className="min-w-0 flex-1">
                          <span className="block text-[13.5px] text-ink-900 truncate">
                            {t(`role.${p.key}`, p.role_label)}
                          </span>
                          <span className="block text-[11.5px] text-ink-500 truncate">
                            {p.authority_limit_eur > 0
                              ? `${t('shell.authorityUpTo')} ${money(p.authority_limit_eur)}`
                              : t('shell.noAuthority')}
                          </span>
                        </span>
                        {on && <Chip tone="blue">{t('shell.current')}</Chip>}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="px-8 py-7 max-w-[1560px] pb-28">{children}</main>
      </div>
    </div>
  )
}
