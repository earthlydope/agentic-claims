import type { ReactNode } from 'react'
import { Badge, Dot } from './ui'

export interface NavItem {
  id: string
  label: string
  group: string
  hint: string
}

export const NAV: NavItem[] = [
  { id: 'overview', label: 'Overview', group: 'Operate', hint: 'Portfolio and the five measures' },
  { id: 'file', label: 'File a claim', group: 'Operate', hint: 'The customer journey' },
  { id: 'claims', label: 'Claims', group: 'Operate', hint: 'Every claim and its run' },
  { id: 'review', label: 'Review queues', group: 'Operate', hint: 'Human authority' },
  { id: 'zerotrust', label: 'Zero trust', group: 'Assure', hint: 'Three pillars, proven' },
  { id: 'agents', label: 'Agents & data', group: 'Assure', hint: 'Nine agents, six models' },
  { id: 'observability', label: 'Observability', group: 'Assure', hint: 'Traces, cost, evals' },
]

export function Shell({
  route, onNavigate, modelMode, defaultRunMode, hybridAgents, agentCount, tenant,
  children, onReset, resetting,
}: {
  route: string
  onNavigate: (id: string) => void
  modelMode: string
  defaultRunMode?: string
  hybridAgents?: number
  agentCount?: number
  tenant: string
  children: ReactNode
  onReset: () => void
  resetting: boolean
}) {
  const live = modelMode === 'live-gemini'
  const hybrid = live && defaultRunMode === 'hybrid'
  const liveCount = hybrid ? hybridAgents ?? 7 : agentCount ?? 9
  const groups = Array.from(new Set(NAV.map((n) => n.group)))

  return (
    <div className="min-h-full flex">
      {/* Sidebar */}
      <aside className="w-[228px] shrink-0 bg-white border-r border-ink-200 flex flex-col sticky top-0 h-screen">
        <div className="px-5 pt-5 pb-4 border-b border-ink-100">
          <div className="flex items-center gap-2">
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
              <rect width="24" height="24" rx="3" fill="#003781" />
              <path d="M6 17V9.6C6 8.2 7.1 7 8.6 7h6.8c1.5 0 2.6 1.2 2.6 2.6V17" stroke="#fff" strokeWidth="1.9" fill="none" strokeLinecap="round" />
              <path d="M6 13.4h12" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" />
            </svg>
            <div className="text-[13px] font-semibold text-ink-900 tracking-[-0.01em]">
              Agentic Claims
            </div>
          </div>
          <div className="text-[11px] text-ink-500 mt-1.5 leading-snug">
            {tenant} · Motor
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto py-3">
          {groups.map((group) => (
            <div key={group} className="mb-4">
              <div className="px-5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-400">
                {group}
              </div>
              {NAV.filter((n) => n.group === group).map((item) => {
                const active = route === item.id || route.startsWith(`${item.id}/`)
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onNavigate(item.id)}
                    className={`w-full text-left px-5 py-[7px] text-[13px] border-l-2 transition-colors ${
                      active
                        ? 'border-az-700 bg-az-50 text-az-700 font-medium'
                        : 'border-transparent text-ink-600 hover:bg-ink-50 hover:text-ink-800'
                    }`}
                  >
                    {item.label}
                  </button>
                )
              })}
            </div>
          ))}
        </nav>

        <div className="px-5 py-4 border-t border-ink-100 space-y-2.5">
          <div className="flex items-center gap-1.5">
            <Dot tone={live ? 'ok' : 'blue'} pulse />
            <span className="text-[11px] text-ink-600">
              {live ? `Gemini · ${liveCount}/${agentCount ?? 9} agents` : 'Deterministic mode'}
            </span>
          </div>
          <p className="text-[10.5px] text-ink-400 leading-[1.45]">
            {live
              ? hybrid
                ? 'Google ADK throughout. The model reasons where there is judgement; the estimate and the task bookkeeping stay deterministic. Switch per run on any claim.'
                : 'Every agent is reasoning against Gemini through Google ADK.'
              : 'Google ADK runs the full loop — tools, plugins, sessions. Set GOOGLE_API_KEY to route reasoning to Gemini.'}
          </p>
          <button
            type="button"
            onClick={onReset}
            disabled={resetting}
            className="text-[11px] text-ink-500 hover:text-az-700 disabled:opacity-50"
          >
            {resetting ? 'Resetting…' : 'Reset demo data'}
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 min-w-0">
        <header className="bg-white border-b border-ink-200 px-8 h-[52px] flex items-center justify-between sticky top-0 z-10">
          <div className="flex items-center gap-2.5 text-[12px] text-ink-500">
            <span className="text-ink-700 font-medium">
              {NAV.find((n) => route === n.id || route.startsWith(`${n.id}/`))?.label ?? 'Overview'}
            </span>
            <span className="text-ink-300">/</span>
            <span>
              {NAV.find((n) => route === n.id || route.startsWith(`${n.id}/`))?.hint ?? ''}
            </span>
          </div>
          <div className="flex items-center gap-2.5">
            <Badge tone="ghost" mono>EU · europe-west4</Badge>
            <Badge tone="blue">Google ADK</Badge>
          </div>
        </header>
        <main className="px-8 py-7 max-w-[1500px]">{children}</main>
      </div>
    </div>
  )
}
