import type { ReactNode } from 'react'

/* ── Layout primitives ───────────────────────────────────────────────── */

export function Card({
  title, subtitle, right, children, className = '', pad = true, dense = false,
}: {
  title?: ReactNode; subtitle?: ReactNode; right?: ReactNode
  children?: ReactNode; className?: string; pad?: boolean; dense?: boolean
}) {
  return (
    <section
      className={`bg-white border border-ink-200 rounded-[6px] ${className}`}
    >
      {(title || right) && (
        <header
          className={`flex items-start justify-between gap-4 border-b border-ink-100 ${
            dense ? 'px-4 py-2.5' : 'px-5 py-3.5'
          }`}
        >
          <div className="min-w-0">
            {title && (
              <h2 className="text-[13px] font-semibold text-ink-800 tracking-[-0.01em]">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="text-[12px] text-ink-500 mt-0.5 leading-snug">{subtitle}</p>
            )}
          </div>
          {right && <div className="shrink-0">{right}</div>}
        </header>
      )}
      <div className={pad ? (dense ? 'p-4' : 'p-5') : ''}>{children}</div>
    </section>
  )
}

export function PageHeader({
  eyebrow, title, lede, right,
}: { eyebrow?: ReactNode; title: string; lede?: string; right?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-6 mb-6">
      <div className="min-w-0">
        {eyebrow && (
          <div className="text-[11px] font-semibold uppercase tracking-[0.09em] text-az-600 mb-1.5">
            {eyebrow}
          </div>
        )}
        <h1 className="text-[22px] font-semibold text-ink-900 tracking-[-0.02em] leading-tight">
          {title}
        </h1>
        {lede && <p className="text-[13px] text-ink-600 mt-1.5 max-w-3xl">{lede}</p>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  )
}

/* ── Badges and status ───────────────────────────────────────────────── */

type Tone = 'neutral' | 'blue' | 'ok' | 'warn' | 'stop' | 'ghost'

const TONES: Record<Tone, string> = {
  neutral: 'bg-ink-100 text-ink-700 border-ink-200',
  blue: 'bg-az-100 text-az-700 border-az-200',
  ok: 'bg-ok-100 text-ok-700 border-ok-100',
  warn: 'bg-warn-100 text-warn-700 border-warn-100',
  stop: 'bg-stop-100 text-stop-700 border-stop-100',
  ghost: 'bg-transparent text-ink-500 border-ink-200',
}

export function Badge({
  children, tone = 'neutral', mono = false, className = '',
}: { children: ReactNode; tone?: Tone; mono?: boolean; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[11px] font-medium leading-4 whitespace-nowrap ${
        TONES[tone]
      } ${mono ? 'font-mono' : ''} ${className}`}
    >
      {children}
    </span>
  )
}

export function Dot({ tone = 'neutral', pulse = false }: { tone?: Tone; pulse?: boolean }) {
  const colour: Record<Tone, string> = {
    neutral: 'bg-ink-400', blue: 'bg-az-500', ok: 'bg-ok-600',
    warn: 'bg-warn-600', stop: 'bg-stop-600', ghost: 'bg-ink-300',
  }
  return (
    <span
      className={`inline-block w-[7px] h-[7px] rounded-full ${colour[tone]} ${
        pulse ? 'pulse-dot' : ''
      }`}
    />
  )
}

export function decisionTone(decision?: string | null): Tone {
  const d = (decision ?? '').toLowerCase()
  if (d.includes('approved')) return 'ok'
  if (d.includes('declined') || d.includes('rejected')) return 'stop'
  if (d.includes('review')) return 'warn'
  if (d.includes('request')) return 'blue'
  return 'neutral'
}

export function statusTone(status?: string | null): Tone {
  const s = (status ?? '').toLowerCase()
  if (['approved', 'ok', 'clean', 'closed'].some((x) => s.includes(x))) return 'ok'
  if (['blocked', 'declined', 'failed', 'stop'].some((x) => s.includes(x))) return 'stop'
  if (['review', 'downgraded', 'awaiting', 'quarantine', 'duplicate'].some((x) => s.includes(x)))
    return 'warn'
  if (['running', 'in_progress', 'fnol'].some((x) => s.includes(x))) return 'blue'
  return 'neutral'
}

/* ── Buttons ─────────────────────────────────────────────────────────── */

export function Button({
  children, onClick, variant = 'primary', size = 'md', disabled, busy, className = '', title,
}: {
  children: ReactNode; onClick?: () => void
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'; disabled?: boolean; busy?: boolean; className?: string; title?: string
}) {
  const variants = {
    primary: 'bg-az-700 text-white border-az-700 hover:bg-az-600 hover:border-az-600',
    secondary: 'bg-white text-ink-700 border-ink-300 hover:bg-ink-50 hover:border-ink-400',
    ghost: 'bg-transparent text-az-700 border-transparent hover:bg-az-50',
    danger: 'bg-white text-stop-700 border-stop-100 hover:bg-stop-100',
  }
  const sizes = { sm: 'px-2.5 py-1 text-[12px]', md: 'px-3.5 py-1.5 text-[13px]' }
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-1.5 rounded border font-medium transition-colors ${
        variants[variant]
      } ${sizes[size]} disabled:opacity-45 disabled:cursor-not-allowed ${className}`}
    >
      {busy && (
        <span className="inline-block w-3 h-3 border-[1.5px] border-current border-t-transparent rounded-full animate-spin" />
      )}
      {children}
    </button>
  )
}

/* ── Data display ────────────────────────────────────────────────────── */

export function Stat({
  label, value, sub, tone = 'neutral', mono = true,
}: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone; mono?: boolean }) {
  const accent: Record<Tone, string> = {
    neutral: 'text-ink-900', blue: 'text-az-700', ok: 'text-ok-700',
    warn: 'text-warn-700', stop: 'text-stop-700', ghost: 'text-ink-500',
  }
  return (
    <div>
      <div className="text-[11px] font-medium uppercase tracking-[0.06em] text-ink-500">
        {label}
      </div>
      <div
        className={`mt-1 text-[20px] font-semibold leading-none tracking-[-0.02em] ${accent[tone]} ${
          mono ? 'tabular' : ''
        }`}
      >
        {value}
      </div>
      {sub && <div className="text-[11.5px] text-ink-500 mt-1.5 leading-snug">{sub}</div>}
    </div>
  )
}

export function Field({
  label, children, mono = false,
}: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-medium uppercase tracking-[0.055em] text-ink-500">
        {label}
      </dt>
      <dd
        className={`text-[13px] text-ink-800 mt-0.5 break-words ${mono ? 'font-mono text-[12px]' : ''}`}
      >
        {children}
      </dd>
    </div>
  )
}

export function Meter({
  value, tone = 'blue', height = 5,
}: { value: number; tone?: Tone; height?: number }) {
  const bar: Record<Tone, string> = {
    neutral: 'bg-ink-400', blue: 'bg-az-500', ok: 'bg-ok-600',
    warn: 'bg-warn-600', stop: 'bg-stop-600', ghost: 'bg-ink-300',
  }
  return (
    <div
      className="w-full bg-ink-100 rounded-full overflow-hidden"
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={`h-full ${bar[tone]} transition-[width] duration-500`}
        style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
      />
    </div>
  )
}

export function CheckRow({
  passed, label, detail, id,
}: { passed: boolean; label: string; detail?: string; id?: string }) {
  return (
    <li className="flex gap-2.5 py-2 border-b border-ink-100 last:border-0">
      <span
        className={`shrink-0 mt-[3px] w-3.5 h-3.5 rounded-full grid place-items-center text-[9px] font-bold text-white ${
          passed ? 'bg-ok-600' : 'bg-stop-600'
        }`}
        aria-hidden
      >
        {passed ? '✓' : '!'}
      </span>
      <div className="min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          {id && <span className="font-mono text-[11px] text-ink-500">{id}</span>}
          <span className="text-[12.5px] font-medium text-ink-800">{label}</span>
          {!passed && <Badge tone="stop">blocked</Badge>}
        </div>
        {detail && <p className="text-[12px] text-ink-600 mt-0.5 leading-snug">{detail}</p>}
      </div>
    </li>
  )
}

export function KeyValueGrid({ children, cols = 3 }: { children: ReactNode; cols?: number }) {
  return (
    <dl
      className="grid gap-x-6 gap-y-4"
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
    >
      {children}
    </dl>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="text-[12.5px] text-ink-500 py-8 text-center border border-dashed border-ink-200 rounded">
      {children}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 text-[12.5px] text-ink-500 py-8 justify-center">
      <span className="inline-block w-3.5 h-3.5 border-[1.5px] border-az-500 border-t-transparent rounded-full animate-spin" />
      {label ?? 'Loading…'}
    </div>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="border border-stop-100 bg-stop-100 text-stop-700 rounded px-3.5 py-2.5 text-[12.5px]">
      {message}
    </div>
  )
}

export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <code className={`font-mono text-[11.5px] text-ink-600 ${className}`}>{children}</code>
  )
}

export function JsonBlock({ value, maxHeight = 320 }: { value: unknown; maxHeight?: number }) {
  return (
    <pre
      className="font-mono text-[11px] leading-[1.55] text-ink-700 bg-ink-50 border border-ink-200 rounded p-3 overflow-auto"
      style={{ maxHeight }}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

/* ── Tables ──────────────────────────────────────────────────────────── */

export function Table({
  head, children, className = '',
}: { head: ReactNode[]; children: ReactNode; className?: string }) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="w-full text-left border-collapse min-w-full">
        <thead>
          <tr>
            {head.map((h, i) => (
              <th
                key={i}
                className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-500 pb-2 pr-4 border-b border-ink-200 whitespace-nowrap"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

export function Td({
  children, mono = false, className = '', align = 'left',
}: { children: ReactNode; mono?: boolean; className?: string; align?: 'left' | 'right' }) {
  return (
    <td
      className={`py-2.5 pr-4 border-b border-ink-100 text-[12.5px] align-top ${
        mono ? 'font-mono text-[11.5px]' : ''
      } ${align === 'right' ? 'text-right tabular' : ''} ${className}`}
    >
      {children}
    </td>
  )
}

/* ── Tabs ────────────────────────────────────────────────────────────── */

export function Tabs<T extends string>({
  tabs, active, onChange,
}: { tabs: { id: T; label: string; count?: number }[]; active: T; onChange: (id: T) => void }) {
  return (
    <div className="flex gap-0.5 border-b border-ink-200 -mb-px overflow-x-auto">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => onChange(t.id)}
          className={`px-3.5 py-2 text-[12.5px] font-medium border-b-2 whitespace-nowrap transition-colors ${
            active === t.id
              ? 'border-az-700 text-az-700'
              : 'border-transparent text-ink-500 hover:text-ink-700'
          }`}
        >
          {t.label}
          {t.count !== undefined && (
            <span className="ml-1.5 text-[11px] text-ink-400 tabular">{t.count}</span>
          )}
        </button>
      ))}
    </div>
  )
}

/* ── Pillar chip ─────────────────────────────────────────────────────── */

export const PILLAR_NAME: Record<number, string> = {
  1: 'Semantic gateway & policy guard',
  2: 'Managed sandbox',
  3: 'Signed actions & ledger',
}

export function PillarChip({ pillar, compact = false }: { pillar: number; compact?: boolean }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 text-[10.5px] font-semibold text-az-700 bg-az-50 border border-az-200 rounded px-1.5 py-0.5 whitespace-nowrap"
      title={PILLAR_NAME[pillar]}
    >
      <span className="font-mono">P{pillar}</span>
      {!compact && <span className="font-normal text-az-600">{PILLAR_NAME[pillar]}</span>}
    </span>
  )
}
