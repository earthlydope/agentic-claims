import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Avatar, Chip, IconButton } from './ui'
import type { Json, Persona } from '../types'

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
  beaker: <path d="M8 3h8M9 3v6l-4 8a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-4-8V3" />,
  gauge: <path d="M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm2.5-3.5L19 6M4 18a9 9 0 1 1 16 0z" />,
  graph: <path d="M6 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm12 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM12 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM7.5 7.5 11 16m6-8.5L13 16" />,
  sparkle: <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />,
}

function Icon({ name, className = '' }: { name: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`w-[18px] h-[18px] shrink-0 ${className}`}
      aria-hidden
    >
      {ICONS[name] ?? ICONS.folder}
    </svg>
  )
}

export function Shell({
  personas, active, onSwitch, feature, onFeature, children, platform,
  onReset, resetting,
}: {
  personas: Persona[]
  active: Persona
  onSwitch: (key: string) => void
  feature: string
  onFeature: (key: string) => void
  children: ReactNode
  platform: Json | null
  onReset: () => void
  resetting: boolean
}) {
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

  const runtime = (platform?.reasoning as Json | undefined)?.default_run_mode as string
  const liveModel = (platform?.harness as Json | undefined)?.live_model_available as boolean
  const current = active.features.find((f) => f.key === feature) ?? active.features[0]

  return (
    <div className="min-h-full flex bg-white">
      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <aside
        className={`shrink-0 flex flex-col sticky top-0 h-screen bg-white transition-[width] duration-200 ${
          collapsed ? 'w-[72px]' : 'w-[260px]'
        }`}
      >
        <div className="h-16 flex items-center gap-2 px-4">
          <IconButton
            title={collapsed ? 'Expand' : 'Collapse'}
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
                Agentic Claims
              </span>
            </div>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-2">
          {active.features.map((f) => {
            const on = f.key === feature
            return (
              <button
                key={f.key}
                type="button"
                title={collapsed ? f.label : f.hint}
                onClick={() => onFeature(f.key)}
                className={`w-full flex items-center gap-3 rounded-full mb-1 transition-colors ${
                  collapsed ? 'justify-center py-2.5' : 'px-4 py-2.5'
                } ${
                  on
                    ? 'bg-air text-az-700 font-medium'
                    : 'text-ink-700 hover:bg-ink-50'
                }`}
              >
                <Icon name={f.icon} />
                {!collapsed && (
                  <span className="text-[13.5px] truncate text-left">{f.label}</span>
                )}
              </button>
            )
          })}
        </nav>

        {!collapsed && (
          <div className="px-5 py-4 space-y-2.5">
            <div className="flex items-center gap-2 text-[12px] text-ink-600">
              <span
                className={`w-2 h-2 rounded-full ${liveModel ? 'bg-ok-600' : 'bg-az-400'}`}
              />
              {liveModel ? `Gemini · ${runtime ?? 'hybrid'}` : 'Deterministic'}
            </div>
            <p className="text-[11px] text-ink-500 leading-[1.5]">
              LangGraph orchestrates. Pydantic&nbsp;AI types every agent output. The
              controls sit outside the model.
            </p>
            <button
              type="button"
              onClick={onReset}
              disabled={resetting}
              className="text-[11.5px] text-ink-500 hover:text-az-700 disabled:opacity-50"
            >
              {resetting ? 'Resetting…' : 'Reset demo data'}
            </button>
          </div>
        )}
      </aside>

      {/* ── Main ────────────────────────────────────────────────── */}
      <div className="flex-1 min-w-0 border-l border-ink-100 bg-ink-50/40">
        <header className="h-16 px-8 flex items-center justify-between bg-white border-b border-ink-100 sticky top-0 z-20">
          <div className="flex items-baseline gap-3 min-w-0">
            <span className="text-[15px] text-ink-900">{current?.label}</span>
            <span className="text-[12.5px] text-ink-500 truncate">{current?.hint}</span>
          </div>

          <div className="flex items-center gap-3">
            <Chip tone="ghost" mono>EU · europe-west4</Chip>

            {/* Persona switcher */}
            <div className="relative" ref={menu}>
              <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                aria-haspopup="menu"
                aria-expanded={open}
                className="flex items-center gap-2.5 pl-2 pr-3 py-1.5 rounded-full hover:bg-ink-50 transition-colors"
              >
                <Avatar initials={active.initials} accent={active.accent} size={32} />
                <span className="text-left hidden sm:block">
                  <span className="block text-[13px] text-ink-900 leading-tight">
                    {active.name}
                  </span>
                  <span className="block text-[11.5px] text-ink-500 leading-tight">
                    {active.role_label}
                  </span>
                </span>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                     strokeLinecap="round" className="w-4 h-4 text-ink-500">
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </button>

              {open && (
                <div
                  role="menu"
                  className="absolute right-0 mt-2 w-[368px] bg-white rounded-2xl elev-3 overflow-hidden fade-up z-30"
                >
                  <div className="px-4 pt-4 pb-2">
                    <div className="text-[12px] text-ink-600">Switch persona</div>
                    <p className="text-[11.5px] text-ink-500 mt-1 leading-relaxed">
                      Each role sees only its own work, and its coworker can only reach the
                      tools that role is allowed to reach.
                    </p>
                  </div>
                  {personas.map((p) => {
                    const on = p.key === active.key
                    return (
                      <button
                        key={p.key}
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          onSwitch(p.key)
                          setOpen(false)
                        }}
                        className={`w-full text-left px-4 py-3 flex items-start gap-3 transition-colors ${
                          on ? 'bg-air' : 'hover:bg-ink-50'
                        }`}
                      >
                        <Avatar initials={p.initials} accent={p.accent} size={34} />
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-2">
                            <span className="text-[13.5px] text-ink-900">{p.name}</span>
                            {on && <Chip tone="blue">current</Chip>}
                          </span>
                          <span className="block text-[12px] text-ink-600">
                            {p.role_label}
                          </span>
                          <span className="block text-[11px] text-ink-500 mt-0.5 italic">
                            {p.role_de}
                          </span>
                          <span className="flex items-center gap-2 mt-1.5">
                            <Chip tone="ghost">
                              {p.authority_limit_eur > 0
                                ? `up to €${p.authority_limit_eur.toLocaleString('de-AT')}`
                                : 'no settlement authority'}
                            </Chip>
                            <span className="text-[11px] text-ink-500">
                              {p.features.length} views
                            </span>
                          </span>
                        </span>
                      </button>
                    )
                  })}
                  <div className="px-4 py-3 bg-ink-50 text-[11.5px] text-ink-600 leading-relaxed">
                    Switching persona changes what the platform shows and what its coworker
                    can do. It is not a display preference — it is the scope.
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="px-8 py-7 max-w-[1560px]">{children}</main>
      </div>
    </div>
  )
}
