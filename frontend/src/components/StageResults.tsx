import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useT } from '../lib/i18n'
import type { Json, TraceEvent } from '../types'

/**
 * What each stage concluded, and — on asking — what it had to work with.
 *
 * The result is always visible; the workings are one click away behind the "?". That split
 * is deliberate. Somebody working a file wants the conclusion and needs to be able to
 * challenge it, but they do not want a wall of JSON in front of the conclusion. So the
 * inputs (which tools were called, with what arguments, and what came back) and the output
 * (the typed result) are there when the question is asked and folded away when it is not.
 *
 * The star records whether a person thought the stage got it right. It is stored per role,
 * so a handler and an assessor can disagree, and it is the honest source for where the
 * automation is actually trusted.
 */

const STAGE_TITLE: Record<string, string> = {
  'evidence.read': 'Documents read',
  'claim.triage': 'Triage',
  'coverage.assess': 'Cover',
  'damage.assess': 'Damage',
  'estimate.build': 'Repair estimate',
  'total.loss': 'Repairability',
  'risk.screen': 'Risk',
  'decision.propose': 'Decision',
  'policy.guard': 'Policy checks',
  'recovery.assess': 'Recovery',
  'comms.draft': 'Customer message',
}

interface StageView {
  id: string
  title: string
  agent: string | null
  output: Json | null
  toolCalls: { tool: string; args: Json; result: Json | null; riskClass?: string }[]
  status: string
  detail: string
  elapsedMs: number
  pillar: number | null
}

/** Fold the event stream into one view per stage. */
function collate(events: TraceEvent[]): StageView[] {
  const byStage = new Map<string, StageView>()
  const order: string[] = []

  const at = (ev: TraceEvent) => {
    const id = (ev as unknown as { stage_id?: string }).stage_id ?? ev.step_id
    if (!id) return null
    if (!byStage.has(id)) {
      byStage.set(id, {
        id,
        title: ev.step_title || STAGE_TITLE[id] || id.replace(/[._]/g, ' '),
        agent: ev.agent,
        output: null,
        toolCalls: [],
        status: 'running',
        detail: '',
        elapsedMs: 0,
        pillar: ev.pillar ?? null,
      })
      order.push(id)
    }
    return byStage.get(id)!
  }

  for (const ev of events) {
    const stage = at(ev)
    if (!stage) continue
    if (ev.agent && !stage.agent) stage.agent = ev.agent
    if (ev.step_title) stage.title = ev.step_title
    if (ev.pillar != null) stage.pillar = ev.pillar

    switch (ev.kind) {
      case 'tool_call':
        stage.toolCalls.push({
          tool: String(ev.data?.tool ?? ''),
          args: (ev.data?.args ?? {}) as Json,
          result: null,
          riskClass: ev.data?.risk_class as string | undefined,
        })
        break
      case 'tool_result': {
        // Attach to the most recent call of the same tool that is still waiting.
        const name = String(ev.data?.tool ?? '')
        const slot = [...stage.toolCalls].reverse()
                      .find((c) => c.tool === name && c.result === null)
        if (slot) slot.result = (ev.data?.result ?? ev.data ?? {}) as Json
        break
      }
      case 'agent_output':
        stage.output = (ev.data?.output ?? ev.data ?? null) as Json | null
        break
      case 'guard':
        stage.output = stage.output ?? ((ev.data?.guard ?? ev.data?.firewall
                                         ?? ev.data) as Json | null)
        stage.status = ev.status
        stage.detail = ev.detail
        break
      case 'step_end':
        stage.status = ev.status
        stage.detail = ev.detail || stage.detail
        stage.elapsedMs = ev.elapsed_ms
        break
      default:
        break
    }
  }

  return order.map((id) => byStage.get(id)!)
}

/** One line of a value, rendered so a number reads as a number. */
function Value({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-ink-400">—</span>
  if (typeof value === 'boolean') {
    return (
      <span className={value ? 'text-ok-700' : 'text-ink-500'}>{value ? 'yes' : 'no'}</span>
    )
  }
  if (typeof value === 'number') {
    return <span className="tabular text-ink-900">{value.toLocaleString('de-AT')}</span>
  }
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-ink-400">—</span>
    if (value.every((v) => typeof v !== 'object')) {
      return <span className="text-ink-800">{value.join(', ')}</span>
    }
    return (
      <ul className="space-y-0.5">
        {value.slice(0, 6).map((v, i) => (
          <li key={i} className="text-ink-700 font-mono text-[11px] truncate">
            {JSON.stringify(v)}
          </li>
        ))}
        {value.length > 6 && (
          <li className="text-ink-400 text-[11px]">+{value.length - 6} more</li>
        )}
      </ul>
    )
  }
  if (typeof value === 'object') {
    return (
      <pre className="font-mono text-[11px] text-ink-700 whitespace-pre-wrap break-all">
        {JSON.stringify(value, null, 1)}
      </pre>
    )
  }
  return <span className="text-ink-800 break-words">{String(value)}</span>
}

/** The fields worth showing first, per stage. Everything else follows underneath. */
const HEADLINE: Record<string, string[]> = {
  'coverage.assess': ['status', 'excess_eur', 'reasoning'],
  'damage.assess': ['severity', 'structural_damage', 'severity_basis'],
  'estimate.build': ['total_cost', 'labour_hours', 'labour_rate_eur', 'within_band'],
  'total.loss': ['verdict', 'ratio', 'threshold', 'reasoning'],
  'risk.screen': ['score', 'above_threshold', 'recommendation'],
  'decision.propose': ['decision', 'settlement_amount_eur', 'reasoning'],
  'claim.triage': ['next_step', 'evidence_completeness', 'missing'],
  'evidence.read': ['document_count', 'quote_total_eur', 'conflicts'],
}

const SKIP = new Set(['summary', 'note', 'citations', 'items', 'panels', 'documents',
                      'signals', 'needs_confirmation', 'unreadable'])

function Output({ stage }: { stage: StageView }) {
  const out = stage.output
  if (!out) return null
  const headline = HEADLINE[stage.id] ?? []
  const rest = Object.keys(out).filter(
    (k) => !headline.includes(k) && !SKIP.has(k) && !k.startsWith('_'),
  )
  const summary = (out.summary ?? out.reasoning ?? out.detail) as string | undefined

  return (
    <div className="space-y-3">
      {!!summary && (
        <p className="text-[12.5px] text-ink-700 leading-relaxed">{summary}</p>
      )}
      <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-2">
        {[...headline.filter((k) => k in out), ...rest].map((k) => (
          <div key={k} className="min-w-0">
            <dt className="text-[11px] text-ink-500">{k.replace(/_/g, ' ')}</dt>
            <dd className="text-[12.5px] mt-0.5"><Value value={(out as Json)[k]} /></dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

export function StageResults({
  events,
  reference,
  persona,
}: {
  events: TraceEvent[]
  reference: string
  persona: string
}) {
  const t = useT()
  const stages = useMemo(() => collate(events), [events])
  const [openWorkings, setOpenWorkings] = useState<Set<string>>(new Set())
  const [verdicts, setVerdicts] = useState<Record<string, boolean>>({})
  const [saved, setSaved] = useState<string | null>(null)

  // The stars come back where this role left them.
  useEffect(() => {
    api
      .stageFeedback(reference, persona)
      .then((d) => {
        const rows = ((d as Json).verdicts ?? {}) as Record<string, { helpful: boolean }>
        setVerdicts(
          Object.fromEntries(Object.entries(rows).map(([k, v]) => [k, v.helpful])),
        )
      })
      .catch(() => undefined)
  }, [reference, persona])

  const rate = async (stage: StageView, helpful: boolean) => {
    setVerdicts((prev) => ({ ...prev, [stage.id]: helpful }))
    setSaved(stage.id)
    window.setTimeout(() => setSaved((s) => (s === stage.id ? null : s)), 1800)
    try {
      await api.rateStage({
        claim_reference: reference,
        stage_id: stage.id,
        agent: stage.agent ?? '',
        persona,
        helpful,
      })
    } catch {
      /* a verdict that could not be stored is not worth an error banner */
    }
  }

  if (!stages.length) return null

  return (
    <div className="space-y-2.5">
      {stages.map((stage) => {
        const showing = openWorkings.has(stage.id)
        const verdict = verdicts[stage.id]
        const failed = stage.status !== 'ok' && stage.status !== 'running'
        return (
          <section
            key={stage.id}
            className="bg-white border border-ink-200 rounded-2xl overflow-hidden"
          >
            <header className="flex items-start gap-3 px-4 py-3">
              <span
                className={`mt-[3px] w-2 h-2 rounded-full shrink-0 ${
                  stage.status === 'running' ? 'bg-az-400 animate-pulse'
                    : failed ? 'bg-warn-600' : 'bg-ok-600'
                }`}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-[13.5px] text-ink-900">{stage.title}</h3>
                  {stage.pillar != null && (
                    <span className="text-[10.5px] px-1.5 py-0.5 rounded-full bg-ink-100
                                     text-ink-600">
                      control
                    </span>
                  )}
                  {stage.elapsedMs > 0 && (
                    <span className="text-[11px] text-ink-400 tabular">
                      {(stage.elapsedMs / 1000).toFixed(1)}s
                    </span>
                  )}
                </div>
                {!!stage.detail && (
                  <p className="text-[12px] text-ink-600 mt-0.5 leading-snug">
                    {stage.detail}
                  </p>
                )}
              </div>

              {/* ── the two controls: how was this reached, and was it right ── */}
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  title={t('cl.whyThis')}
                  aria-expanded={showing}
                  onClick={() =>
                    setOpenWorkings((prev) => {
                      const next = new Set(prev)
                      if (next.has(stage.id)) next.delete(stage.id)
                      else next.add(stage.id)
                      return next
                    })
                  }
                  className={`w-7 h-7 rounded-full flex items-center justify-center
                              text-[13px] font-medium transition-colors ${
                    showing ? 'bg-air text-az-700' : 'text-ink-400 hover:bg-ink-50 hover:text-ink-700'
                  }`}
                >
                  ?
                </button>
                <button
                  type="button"
                  title={t('cl.helpful')}
                  onClick={() => void rate(stage, true)}
                  className={`w-7 h-7 rounded-full flex items-center justify-center
                              transition-colors ${
                    verdict === true
                      ? 'text-amber-600' : 'text-ink-300 hover:text-amber-600 hover:bg-ink-50'
                  }`}
                >
                  <svg viewBox="0 0 24 24" strokeWidth="1.7" stroke="currentColor"
                       fill={verdict === true ? 'currentColor' : 'none'}
                       strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
                    <path d="M12 3.5l2.6 5.7 6.2.7-4.6 4.2 1.3 6.1L12 17l-5.5 3.2 1.3-6.1L3.2 9.9l6.2-.7z" />
                  </svg>
                </button>
                <button
                  type="button"
                  title={t('cl.notHelpful')}
                  onClick={() => void rate(stage, false)}
                  className={`w-7 h-7 rounded-full flex items-center justify-center
                              transition-colors ${
                    verdict === false
                      ? 'text-stop-600 bg-stop-100'
                      : 'text-ink-300 hover:text-stop-600 hover:bg-ink-50'
                  }`}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                       strokeLinecap="round" className="w-4 h-4">
                    <path d="M6 6l12 12M18 6L6 18" />
                  </svg>
                </button>
              </div>
            </header>

            {saved === stage.id && (
              <div className="px-4 pb-1 -mt-1 text-[11px] text-ok-700">{t('cl.rated')}</div>
            )}

            {/* the result, always */}
            {stage.output && (
              <div className="px-4 pb-3.5">
                <Output stage={stage} />
              </div>
            )}

            {/* the workings, on asking */}
            {showing && (
              <div className="border-t border-ink-100 bg-ink-50/60 px-4 py-3.5 space-y-4">
                <div>
                  <div className="text-[11px] text-ink-500 uppercase tracking-wide mb-2">
                    {t('cl.whatWentIn')}
                  </div>
                  {stage.toolCalls.length === 0 ? (
                    <p className="text-[12px] text-ink-500">
                      Nothing was read from the business data for this stage.
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {stage.toolCalls.map((call, i) => (
                        <li key={`${call.tool}-${i}`} className="rounded-xl bg-white
                                                                 border border-ink-200 p-3">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-mono text-[11.5px] text-az-700">
                              {call.tool}
                            </span>
                            {!!call.riskClass && (
                              <span className="text-[10.5px] px-1.5 py-0.5 rounded-full
                                               bg-ink-100 text-ink-600">
                                {call.riskClass}
                              </span>
                            )}
                          </div>
                          {!!Object.keys(call.args ?? {}).length && (
                            <div className="mt-1.5 text-[11px] text-ink-600 font-mono
                                            break-all">
                              {JSON.stringify(call.args)}
                            </div>
                          )}
                          {call.result && (
                            <pre className="mt-2 text-[11px] text-ink-700 font-mono
                                            whitespace-pre-wrap break-all max-h-40
                                            overflow-y-auto">
                              {JSON.stringify(call.result, null, 1)}
                            </pre>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div>
                  <div className="text-[11px] text-ink-500 uppercase tracking-wide mb-2">
                    {t('cl.whatCameOut')}
                  </div>
                  <pre className="text-[11px] text-ink-700 font-mono whitespace-pre-wrap
                                  break-all bg-white border border-ink-200 rounded-xl p-3
                                  max-h-60 overflow-y-auto">
                    {JSON.stringify(stage.output ?? {}, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </section>
        )
      })}
    </div>
  )
}
