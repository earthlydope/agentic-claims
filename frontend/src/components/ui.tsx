import { useState } from 'react'
import type { ReactNode } from 'react'

/* ── Layout ──────────────────────────────────────────────────────────── */

export function Card({
  title, subtitle, right, children, className = '', pad = true, flush = false,
  dense = false,
}: {
  title?: ReactNode; subtitle?: ReactNode; right?: ReactNode
  children?: ReactNode; className?: string; pad?: boolean; flush?: boolean
  /** Tighter padding for cards that sit in a dense grid. */
  dense?: boolean
}) {
  return (
    <section
      className={`bg-white border border-ink-200 rounded-2xl overflow-hidden ${className}`}
    >
      {(title || right) && (
        <header
          className={`flex items-start justify-between gap-4 ${
            dense ? 'px-4 pt-3.5 pb-2.5' : 'px-5 pt-4 pb-3'
          }`}
        >
          <div className="min-w-0">
            {title && (
              <h2 className="text-[14px] font-medium text-ink-900 tracking-[-0.01em]">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="text-[12.5px] text-ink-600 mt-1 leading-relaxed max-w-3xl">
                {subtitle}
              </p>
            )}
          </div>
          {right && <div className="shrink-0">{right}</div>}
        </header>
      )}
      <div
        className={
          pad
            ? dense
              ? title
                ? 'px-4 pb-4'
                : 'p-4'
              : flush
                ? 'px-5 pb-5'
                : title
                  ? 'px-5 pb-5'
                  : 'p-5'
            : ''
        }
      >
        {children}
      </div>
    </section>
  )
}

export function PageHeader({
  eyebrow, title, lede, right,
}: { eyebrow?: ReactNode; title: string; lede?: string; right?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-8 mb-6">
      <div className="min-w-0">
        {eyebrow && (
          <div className="text-[12px] text-ink-600 mb-1.5">{eyebrow}</div>
        )}
        <h1 className="text-[26px] font-normal text-ink-900 tracking-[-0.02em] leading-tight">
          {title}
        </h1>
        {lede && (
          <p className="text-[13.5px] text-ink-600 mt-2 max-w-3xl leading-relaxed">{lede}</p>
        )}
      </div>
      {right && <div className="shrink-0 flex items-center gap-2">{right}</div>}
    </div>
  )
}

/* ── Badges ──────────────────────────────────────────────────────────── */

export type Tone = 'neutral' | 'blue' | 'ok' | 'warn' | 'stop' | 'ghost'

const CHIP: Record<Tone, string> = {
  neutral: 'bg-ink-100 text-ink-700',
  blue: 'bg-air text-info-700',
  ok: 'bg-ok-100 text-ok-700',
  warn: 'bg-warn-100 text-warn-700',
  stop: 'bg-stop-100 text-stop-700',
  ghost: 'bg-transparent text-ink-600 ring-1 ring-inset ring-ink-200',
}

export function Chip({
  children, tone = 'neutral', mono = false, className = '',
}: { children: ReactNode; tone?: Tone; mono?: boolean; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-[3px] rounded-full text-[11.5px] font-medium leading-4 whitespace-nowrap ${
        CHIP[tone]
      } ${mono ? 'font-mono text-[11px]' : ''} ${className}`}
    >
      {children}
    </span>
  )
}

export const Badge = Chip

export function Dot({ tone = 'neutral', pulse = false }: { tone?: Tone; pulse?: boolean }) {
  const colour: Record<Tone, string> = {
    neutral: 'bg-ink-400', blue: 'bg-az-500', ok: 'bg-ok-600',
    warn: 'bg-warn-600', stop: 'bg-stop-600', ghost: 'bg-ink-300',
  }
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${colour[tone]} ${pulse ? 'pulse-dot' : ''}`}
    />
  )
}

export function decisionTone(decision?: string | null): Tone {
  const d = (decision ?? '').toLowerCase()
  if (d.includes('approved') || d.includes('settled')) return 'ok'
  if (d.includes('declined') || d.includes('rejected')) return 'stop'
  if (d.includes('review') || d.includes('total loss')) return 'warn'
  if (d.includes('request') || d.includes('waiting')) return 'blue'
  return 'neutral'
}

export function toneOf(tone?: string | null): Tone {
  const t = (tone ?? '').toLowerCase()
  if (['ok', 'ok'].includes(t)) return 'ok'
  if (t === 'warn') return 'warn'
  if (t === 'stop') return 'stop'
  if (t === 'info') return 'blue'
  return 'neutral'
}

export function statusTone(status?: string | null): Tone {
  const s = (status ?? '').toLowerCase()
  if (['approved', 'settled', 'clean', 'closed', 'ok'].some((x) => s.includes(x))) return 'ok'
  if (['blocked', 'declined', 'failed', 'investigation'].some((x) => s.includes(x)))
    return 'stop'
  if (['review', 'downgraded', 'awaiting', 'quarantine', 'total'].some((x) => s.includes(x)))
    return 'warn'
  if (['running', 'progress', 'reported', 'assessing'].some((x) => s.includes(x))) return 'blue'
  return 'neutral'
}

/* ── Buttons ─────────────────────────────────────────────────────────── */

export function Button({
  children, onClick, variant = 'primary', size = 'md', disabled, busy,
  className = '', title, type = 'button',
}: {
  children: ReactNode; onClick?: () => void
  variant?: 'primary' | 'secondary' | 'text' | 'ghost' | 'danger'
  size?: 'sm' | 'md'; disabled?: boolean; busy?: boolean; className?: string
  title?: string; type?: 'button' | 'submit'
}) {
  const variants = {
    primary: 'bg-az-700 text-white hover:bg-az-600 elev-1 hover:elev-2',
    secondary: 'bg-white text-az-700 ring-1 ring-inset ring-ink-300 hover:bg-az-50',
    text: 'bg-transparent text-az-700 hover:bg-az-50',
    // `ghost` is the same low-emphasis button under an older name.
    ghost: 'bg-transparent text-az-700 hover:bg-az-50',
    danger: 'bg-white text-stop-700 ring-1 ring-inset ring-stop-100 hover:bg-stop-100',
  }
  const sizes = { sm: 'px-3 py-1.5 text-[12.5px]', md: 'px-5 py-2 text-[13.5px]' }
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-full font-medium transition-all ${
        variants[variant]
      } ${sizes[size]} disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none ${className}`}
    >
      {busy && (
        <span className="inline-block w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
      )}
      {children}
    </button>
  )
}

export function IconButton({
  children, onClick, title, active = false, className = '',
}: {
  children: ReactNode; onClick?: () => void; title?: string; active?: boolean
  className?: string
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`w-9 h-9 grid place-items-center rounded-full transition-colors ${
        active ? 'bg-air text-az-700' : 'text-ink-600 hover:bg-ink-50'
      } ${className}`}
    >
      {children}
    </button>
  )
}

/* ── Data ────────────────────────────────────────────────────────────── */

export function Stat({
  label, value, sub, tone = 'neutral', mono = true,
}: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone; mono?: boolean }) {
  const accent: Record<Tone, string> = {
    neutral: 'text-ink-900', blue: 'text-az-700', ok: 'text-ok-700',
    warn: 'text-warn-700', stop: 'text-stop-700', ghost: 'text-ink-500',
  }
  return (
    <div>
      <div className="text-[12px] text-ink-600">{label}</div>
      <div
        className={`mt-1 text-[24px] font-normal leading-none tracking-[-0.02em] ${accent[tone]} ${
          mono ? 'tabular' : ''
        }`}
      >
        {value}
      </div>
      {sub && <div className="text-[12px] text-ink-500 mt-2 leading-snug">{sub}</div>}
    </div>
  )
}

export function Field({
  label, children, mono = false,
}: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[12px] text-ink-600">{label}</dt>
      <dd
        className={`text-[13.5px] text-ink-900 mt-0.5 break-words ${
          mono ? 'font-mono text-[12.5px]' : ''
        }`}
      >
        {children}
      </dd>
    </div>
  )
}

export function KeyValueGrid({ children, cols = 3 }: { children: ReactNode; cols?: number }) {
  return (
    <dl className="grid gap-x-8 gap-y-4" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
      {children}
    </dl>
  )
}

/** A rounded meter, the way Studio draws a quota bar. */
export function Meter({
  value, tone = 'blue', height = 6, over = false,
}: { value: number; tone?: Tone; height?: number; over?: boolean }) {
  const bar: Record<Tone, string> = {
    neutral: 'bg-ink-400', blue: 'bg-az-500', ok: 'bg-ok-600',
    warn: 'bg-warn-600', stop: 'bg-stop-600', ghost: 'bg-ink-300',
  }
  const clamped = Math.max(0, Math.min(1, value))
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
        className={`h-full rounded-full transition-[width] duration-500 ${
          over ? 'bg-stop-600' : bar[tone]
        }`}
        style={{ width: `${clamped * 100}%` }}
      />
    </div>
  )
}

export function CheckRow({
  passed, label, detail, id, remedy,
}: { passed: boolean; label: string; detail?: string; id?: string; remedy?: string }) {
  return (
    <li className="flex gap-3 py-2.5 border-b border-ink-100 last:border-0">
      <span
        className={`shrink-0 mt-0.5 w-4 h-4 rounded-full grid place-items-center text-[10px] font-bold text-white ${
          passed ? 'bg-ok-600' : 'bg-stop-600'
        }`}
        aria-hidden
      >
        {passed ? '✓' : '!'}
      </span>
      <div className="min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          {id && <span className="font-mono text-[11.5px] text-ink-500">{id}</span>}
          <span className="text-[13px] text-ink-900">{label}</span>
        </div>
        {detail && <p className="text-[12.5px] text-ink-600 mt-0.5 leading-relaxed">{detail}</p>}
        {remedy && (
          <p className="text-[12.5px] text-az-700 mt-1 leading-relaxed">→ {remedy}</p>
        )}
      </div>
    </li>
  )
}

export function Empty({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="text-center py-12 px-6">
      <p className="text-[13.5px] text-ink-600 max-w-md mx-auto leading-relaxed">{children}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-[13px] text-ink-600 py-12 justify-center">
      <span className="inline-block w-4 h-4 border-2 border-az-500 border-t-transparent rounded-full animate-spin" />
      {label ?? 'Loading…'}
    </div>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 bg-stop-100 text-stop-700 rounded-xl px-4 py-3 text-[13px] leading-relaxed">
      <span className="shrink-0 mt-0.5 w-4 h-4 rounded-full bg-stop-600 text-white grid place-items-center text-[10px] font-bold">
        !
      </span>
      <span>{message}</span>
    </div>
  )
}

export function Notice({
  tone = 'blue', title, children, action,
}: { tone?: Tone; title?: string; children: ReactNode; action?: ReactNode }) {
  const bg: Record<Tone, string> = {
    neutral: 'bg-ink-50 text-ink-700', blue: 'bg-air text-info-700',
    ok: 'bg-ok-100 text-ok-700', warn: 'bg-warn-100 text-warn-700',
    stop: 'bg-stop-100 text-stop-700', ghost: 'bg-white text-ink-700',
  }
  return (
    <div className={`rounded-xl px-4 py-3.5 ${bg[tone]}`}>
      {title && <div className="text-[13px] font-medium mb-1">{title}</div>}
      <div className="text-[12.5px] leading-relaxed">{children}</div>
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <code className={`font-mono text-[12px] ${className}`}>{children}</code>
}

export function JsonBlock({ value, maxHeight = 320 }: { value: unknown; maxHeight?: number }) {
  return (
    <pre
      className="font-mono text-[11.5px] leading-[1.6] text-ink-700 bg-ink-50 rounded-xl p-4 overflow-auto"
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
                className="text-[12px] font-medium text-ink-600 pb-2.5 pr-5 border-b border-ink-200 whitespace-nowrap"
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
      className={`py-3 pr-5 border-b border-ink-100 text-[13px] align-top text-ink-800 ${
        mono ? 'font-mono text-[12px]' : ''
      } ${align === 'right' ? 'text-right tabular' : ''} ${className}`}
    >
      {children}
    </td>
  )
}

/* ── Tabs — Studio's underline style ─────────────────────────────────── */

export function Tabs<T extends string>({
  tabs, active, onChange,
}: { tabs: { id: T; label: string; count?: number }[]; active: T; onChange: (id: T) => void }) {
  return (
    <div className="flex gap-1 border-b border-ink-200 -mb-px overflow-x-auto">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => onChange(t.id)}
          className={`px-4 py-2.5 text-[13px] font-medium border-b-[3px] rounded-t-lg whitespace-nowrap transition-colors ${
            active === t.id
              ? 'border-az-700 text-az-700 bg-az-50/60'
              : 'border-transparent text-ink-600 hover:text-ink-900 hover:bg-ink-50'
          }`}
        >
          {t.label}
          {t.count !== undefined && (
            <span className="ml-2 text-[11.5px] text-ink-500 tabular">{t.count}</span>
          )}
        </button>
      ))}
    </div>
  )
}

/* ── Segmented control ───────────────────────────────────────────────── */

export function Segmented<T extends string>({
  options, value, onChange, size = 'md',
}: {
  options: { id: T; label: string; hint?: string }[]
  value: T
  onChange: (id: T) => void
  size?: 'sm' | 'md'
}) {
  return (
    <div className="inline-flex bg-ink-50 rounded-full p-0.5">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          title={o.hint}
          onClick={() => onChange(o.id)}
          className={`rounded-full font-medium transition-all ${
            size === 'sm' ? 'px-3 py-1 text-[12px]' : 'px-4 py-1.5 text-[12.5px]'
          } ${
            value === o.id
              ? 'bg-white text-az-700 elev-1'
              : 'text-ink-600 hover:text-ink-900'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/* ── Pillars ─────────────────────────────────────────────────────────── */

export const PILLAR_NAME: Record<number, string> = {
  1: 'Semantic gateway & policy guard',
  2: 'Managed sandbox',
  3: 'Signed actions & ledger',
}

export function PillarChip({ pillar, compact = false }: { pillar: number; compact?: boolean }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 text-[11px] font-medium text-az-700 bg-az-50 rounded-full px-2 py-[3px] whitespace-nowrap"
      title={PILLAR_NAME[pillar]}
    >
      <span className="font-mono">P{pillar}</span>
      {!compact && <span className="font-normal text-az-600">{PILLAR_NAME[pillar]}</span>}
    </span>
  )
}

/* ── Avatar ──────────────────────────────────────────────────────────── */

const ACCENT: Record<string, string> = {
  blue: 'bg-az-700 text-white',
  teal: 'bg-teal-600 text-white',
  amber: 'bg-amber-600 text-white',
  indigo: 'bg-indigo-600 text-white',
  rose: 'bg-rose-600 text-white',
  slate: 'bg-slate-600 text-white',
}

export function Avatar({
  initials, accent = 'blue', size = 32,
}: { initials: string; accent?: string; size?: number }) {
  return (
    <span
      className={`inline-grid place-items-center rounded-full font-medium shrink-0 ${
        ACCENT[accent] ?? ACCENT.blue
      }`}
      style={{ width: size, height: size, fontSize: size * 0.36 }}
    >
      {initials}
    </span>
  )
}

export const ACCENT_TEXT: Record<string, string> = {
  blue: 'text-az-700', teal: 'text-teal-600', amber: 'text-amber-600',
  indigo: 'text-indigo-600', rose: 'text-rose-600', slate: 'text-slate-600',
}

export const ACCENT_WASH: Record<string, string> = {
  blue: 'bg-az-50', teal: 'bg-teal-100', amber: 'bg-amber-100',
  indigo: 'bg-indigo-100', rose: 'bg-rose-100', slate: 'bg-slate-100',
}

/* ── Inputs ──────────────────────────────────────────────────────────── */

export function TextInput({
  value, onChange, placeholder, mono = false, className = '', onEnter,
}: {
  value: string; onChange: (v: string) => void; placeholder?: string
  mono?: boolean; className?: string; onEnter?: () => void
}) {
  return (
    <input
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' && onEnter) onEnter()
      }}
      className={`w-full bg-white border border-ink-300 rounded-xl px-4 py-2.5 text-[13.5px] placeholder:text-ink-400 focus:outline-none focus:border-az-500 focus:ring-2 focus:ring-air ${
        mono ? 'font-mono text-[12.5px]' : ''
      } ${className}`}
    />
  )
}

export function Select({
  value, onChange, options, className = '', title,
}: {
  value: string; onChange: (v: string) => void
  options: { value: string; label: string }[]; className?: string; title?: string
}) {
  return (
    <select
      value={value}
      title={title}
      onChange={(e) => onChange(e.target.value)}
      className={`bg-white border border-ink-300 rounded-xl px-3 py-2 text-[13px] text-ink-800 focus:outline-none focus:border-az-500 focus:ring-2 focus:ring-air ${className}`}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}


/**
 * Copy to clipboard, with the confirmation on the button itself.
 *
 * A message a handler is going to paste into their own mail client needs to leave here in
 * one click, and the confirmation has to be where the eye already is — a toast in the
 * corner is a confirmation nobody sees.
 */
export function CopyButton({
  text,
  label = 'Copy',
  copiedLabel = 'Copied',
  className = '',
}: {
  text: string
  label?: string
  copiedLabel?: string
  className?: string
}) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Clipboard access is refused in some embedded contexts; the textarea route still
      // works there and is worth keeping rather than failing silently.
      const scratch = document.createElement('textarea')
      scratch.value = text
      scratch.setAttribute('readonly', '')
      scratch.style.position = 'fixed'
      scratch.style.opacity = '0'
      document.body.appendChild(scratch)
      scratch.select()
      try {
        document.execCommand('copy')
      } catch {
        /* nothing further to try */
      }
      document.body.removeChild(scratch)
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  return (
    <button
      type="button"
      onClick={() => void copy()}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border
                  text-[12px] transition-colors ${
        copied
          ? 'border-ok-600 text-ok-700 bg-ok-100'
          : 'border-ink-200 text-ink-700 hover:bg-ink-50'
      } ${className}`}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
           strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5">
        {copied
          ? <path d="m4 12.5 5 5L20 6.5" />
          : <><rect x="9" y="9" width="11" height="11" rx="2" />
              <path d="M15 5H6a2 2 0 0 0-2 2v9" /></>}
      </svg>
      {copied ? copiedLabel : label}
    </button>
  )
}
