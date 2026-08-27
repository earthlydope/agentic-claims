import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, streamRun } from '../api'
import {
  Badge, Card, CheckRow, CopyButton, decisionTone, Dot, Empty, ErrorNote, Field,
  JsonBlock, KeyValueGrid, Meter, Mono, PageHeader, PillarChip, Spinner, Stat,
  statusTone, Table, Tabs, Td,
} from '../components/ui'
import { StageResults } from '../components/StageResults'
import { useEnum, useT } from '../lib/i18n'
import { eur, ms, num, shortHash, when } from '../lib/format'
import type { Json, Step, TraceEvent } from '../types'

type Tab = 'results' | 'run' | 'evidence' | 'assessment' | 'decision' | 'customer' | 'ledger'

const KIND_LABEL: Record<string, string> = {
  run_start: 'run started', guard: 'policy control', preflight: 'evidence preflight',
  step_start: 'agent started', tool_call: 'tool call', tool_result: 'tool result',
  agent_output: 'agent output', security: 'security event', step_end: 'agent complete',
  sign: 'action signed', write: 'write gateway', run_end: 'run finished',
}

export function ClaimWorkbench({
  reference, onBack, persona,
}: { reference: string; onBack: () => void; persona?: { key: string; role_label: string } }) {
  const t = useT()
  const label = useEnum()
  const [detail, setDetail] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [steps, setSteps] = useState<Step[]>([])
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [running, setRunning] = useState(false)
  const [tab, setTab] = useState<Tab>('results')
  const [selectedStep, setSelectedStep] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const started = useRef(false)
  const stopRef = useRef<(() => void) | null>(null)
  const feedRef = useRef<HTMLDivElement>(null)

  const load = useCallback(() => {
    api
      .claim(reference)
      .then((d) => {
        setDetail(d)
        // A claim that was already worked carries its trace. Seed the feed from it, so
        // opening a file shows what was found rather than an empty panel — but never
        // over a live stream that is already producing events.
        const recorded = ((d as Json).trace ?? []) as TraceEvent[]
        setEvents((prev) => (prev.length ? prev : recorded))
      })
      .catch((e: Error) => setError(e.message))
  }, [reference])

  useEffect(() => {
    load()
    api
      .lifecycle()
      .then((l) => {
        const stages = (l as { stages: Json[] }).stages ?? []
        setSteps(
          stages.map((st) => ({
            no: st.no as number,
            id: st.id as string,
            title: st.title as string,
            lane: st.lane as string,
            pillar: (st.pillar as number | null) ?? null,
          })),
        )
      })
      .catch(() => undefined)
  }, [load])

  useEffect(() => () => stopRef.current?.(), [])

  // Follow the feed while a run is streaming.
  useEffect(() => {
    if (running && feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight
    }
  }, [events, running])

  const start = useCallback(() => {
    setEvents([])
    setExpanded(new Set())
    setSelectedStep(null)
    setRunning(true)
    stopRef.current = streamRun(
      reference,
      (ev) => setEvents((prev) => [...prev, ev]),
      () => {
        setRunning(false)
        load()
      },
      (message) => {
        setError(message)
        setRunning(false)
      },
      'system',
      { persona: persona?.key },
    )
  }, [reference, load, persona?.key])

  /**
   * A file nobody has worked yet works itself when it is opened.
   *
   * Opening a claim is the signal that somebody wants to know where it stands, and making
   * them press something first is the step this platform exists to remove. It runs once per
   * mounted file — `started` guards against React re-invoking the effect — and only where
   * nothing has been recorded against the claim before.
   */
  useEffect(() => {
    if (started.current || !detail) return
    const worked = ((detail.trace as Json[] | undefined)?.length ?? 0) > 0
      || Boolean((detail.claim as Json | undefined)?.decision)
    if (worked) return
    started.current = true
    start()
  }, [detail, start])

  const runEnd = events.find((e) => e.kind === 'run_end')
  const guardEvent = [...events].reverse().find((e) => e.step_id === 'policy.guard' && e.kind === 'guard')

  const stepState = useMemo(() => {
    const state: Record<string, { status: string; agent?: string | null; ms?: number }> = {}
    for (const ev of events) {
      const stage = (ev as unknown as { stage_id?: string }).stage_id ?? ev.step_id
      if (!stage) continue
      const current = state[stage]
      if (ev.kind === 'step_start' || ev.kind === 'run_start') {
        state[stage] = { status: 'running', agent: ev.agent }
      } else if (ev.kind === 'step_end' || ev.kind === 'run_end') {
        state[stage] = {
          status: ev.status === 'ok' ? 'done' : ev.status,
          agent: current?.agent ?? ev.agent,
          ms: ev.elapsed_ms,
        }
      } else if (['guard', 'preflight', 'sign', 'write'].includes(ev.kind)) {
        state[stage] = {
          status: ev.status === 'ok' ? 'done' : ev.status,
          agent: ev.agent, ms: ev.elapsed_ms,
        }
      } else if (!current) {
        state[stage] = { status: 'running', agent: ev.agent }
      }
    }
    return state
  }, [events])

  const shownEvents = useMemo(
    () =>
      selectedStep
        ? events.filter(
            (e) =>
              ((e as unknown as { stage_id?: string }).stage_id ?? e.step_id) ===
              selectedStep,
          )
        : events,
    [events, selectedStep],
  )

  if (error && !detail) return <ErrorNote message={error} />
  if (!detail) return <Spinner />

  const claim = detail.claim as Json
  const persisted = {
    coverage: detail.coverage as Json | null,
    estimate: detail.estimate as Json | null,
    risk: detail.risk as Json,
    documents: detail.documents as Json[],
    tasks: detail.tasks as Json[],
    messages: detail.messages as Json[],
    timeline: detail.timeline as Json[],
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <button type="button" onClick={onBack} className="hover:underline">
              {t('cw2.back')}
            </button>
            {' / '}
            {claim.reference as string}
          </>
        }
        title={`${claim.policyholder?.name ?? 'Claim'} · ${(claim.incident_type as string ?? '').replace(/_/g, ' ')}`}
        lede={claim.scenario ? (claim.scenario as Json).headline as string : undefined}
        right={
          <div className="flex items-center gap-2.5">
            {claim.decision && (
              <Badge tone={decisionTone(claim.decision as string)}>
                {label(claim.decision as string)}
              </Badge>
            )}
            {/* Nothing to press. The analysis starts on notification; this only says
                whether it is still going. */}
            {running && (
              <span className="flex items-center gap-2 text-[12.5px] text-az-700">
                <span className="inline-block w-3.5 h-3.5 border-2 border-az-500
                                 border-t-transparent rounded-full animate-spin" />
                {t('cw2.working')}
              </span>
            )}
          </div>
        }
      />

      {error && (
        <div className="mb-4">
          <ErrorNote message={error} />
        </div>
      )}

      {/* Claim identity */}
      <Card className="mb-5" dense>
        <KeyValueGrid cols={6}>
          <Field label={t('cw2.policyholder')}>
            {claim.policyholder?.name}
            <div className="text-[11px] text-ink-500">
              {claim.policyholder?.city}, {claim.policyholder?.region} ·{' '}
              {(claim.language as string).toUpperCase()}
            </div>
          </Field>
          <Field label={t('cw2.policy')}>
            {claim.policy?.product}
            <div className="text-[11px] text-ink-500 font-mono">
              {claim.policy?.policy_number}
            </div>
          </Field>
          <Field label={t('cw2.vehicle')}>
            {claim.vehicle?.make} {claim.vehicle?.model}
            <div className="text-[11px] text-ink-500 font-mono">
              {claim.vehicle?.plate} · {claim.vehicle?.year}
            </div>
          </Field>
          <Field label={t('cw2.excess')}>{eur(claim.policy?.excess_eur)}</Field>
          <Field label={t('cw2.reported')}>
            {when(claim.reported_at as string)}
            <div className="text-[11px] text-ink-500">via {claim.channel as string}</div>
          </Field>
          <Field label={t('cw2.flags')}>
            <div className="flex flex-wrap gap-1">
              {claim.injury_reported ? <Badge tone="stop">injury</Badge> : null}
              {claim.structural_damage ? <Badge tone="warn">structural</Badge> : null}
              {claim.third_party_involved ? <Badge tone="neutral">third party</Badge> : null}
              {(claim.fraud_score as number) > 0.55 ? (
                <Badge tone="stop">risk {(claim.fraud_score as number).toFixed(2)}</Badge>
              ) : null}
              {!claim.injury_reported &&
                !claim.structural_damage &&
                !claim.third_party_involved &&
                (claim.fraud_score as number) <= 0.55 && (
                  <span className="text-ink-400 text-[12px]">none</span>
                )}
            </div>
          </Field>
        </KeyValueGrid>
        {claim.fnol_text ? (
          <div className="mt-4 pt-4 border-t border-ink-100">
            <div className="text-[11px] font-medium uppercase tracking-[0.055em] text-ink-500 mb-1.5">
              {t('cw2.customerWrote')}
            </div>
            <p className="text-[13px] text-ink-700 leading-relaxed max-w-4xl italic">
              “{claim.fnol_text as string}”
            </p>
          </div>
        ) : null}
      </Card>

      <div className="border-b border-ink-200 mb-5">
        <Tabs
          tabs={[
            { id: 'results' as Tab, label: t('cw2.tabResults') },
            { id: 'run' as Tab, label: t('cw2.tabRun'), count: events.length || undefined },
            { id: 'evidence' as Tab, label: t('cw2.tabEvidence'), count: persisted.documents.length },
            { id: 'assessment' as Tab, label: t('cw2.tabAssessment') },
            { id: 'decision' as Tab, label: t('cw2.tabDecision') },
            { id: 'customer' as Tab, label: t('cw2.tabCustomer'), count: persisted.messages.length },
            { id: 'ledger' as Tab, label: t('cw2.tabLedger') },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      {tab === 'results' && (
        events.length === 0 ? (
          <Card>
            <Empty>
              {running
                ? t('cw2.readingNow')
                : t('cw2.nothingAssessed')}
            </Empty>
          </Card>
        ) : (
          <StageResults
            events={events}
            reference={reference}
            persona={persona?.key ?? 'claim_handler'}
          />
        )
      )}

      {tab === 'run' && (
        <RunConsole
          steps={steps}
          stepState={stepState}
          events={shownEvents}
          allEvents={events}
          running={running}
          runEnd={runEnd}
          guardEvent={guardEvent}
          selectedStep={selectedStep}
          onSelectStep={setSelectedStep}
          expanded={expanded}
          onToggle={(seq) =>
            setExpanded((prev) => {
              const next = new Set(prev)
              next.has(seq) ? next.delete(seq) : next.add(seq)
              return next
            })
          }
          feedRef={feedRef}
        />
      )}

      {tab === 'evidence' && <EvidencePanel documents={persisted.documents} />}
      {tab === 'assessment' && (
        <AssessmentPanel
          coverage={persisted.coverage}
          estimate={persisted.estimate}
          risk={persisted.risk}
          events={events}
        />
      )}
      {tab === 'decision' && (
        <DecisionPanel guardEvent={guardEvent} runEnd={runEnd} tasks={persisted.tasks} />
      )}
      {tab === 'customer' && (
        <CustomerPanel messages={persisted.messages} timeline={persisted.timeline} />
      )}
      {tab === 'ledger' && <LedgerPanel reference={reference} events={events} />}
    </>
  )
}

/* ── Run console ─────────────────────────────────────────────────────── */

function RunConsole({
  steps, stepState, events, allEvents, running, runEnd, guardEvent, selectedStep,
  onSelectStep, expanded, onToggle, feedRef,
}: {
  steps: Step[]
  stepState: Record<string, { status: string; agent?: string | null; ms?: number }>
  events: TraceEvent[]
  allEvents: TraceEvent[]
  running: boolean
  runEnd?: TraceEvent
  guardEvent?: TraceEvent
  selectedStep: string | null
  onSelectStep: (s: string | null) => void
  expanded: Set<number>
  onToggle: (seq: number) => void
  feedRef: React.RefObject<HTMLDivElement | null>
}) {
  const t = useT()
  const summary = runEnd?.data?.summary as Json | undefined
  const lanes: Record<string, { label: string; tone: string }> = {
    customer: { label: 'Customer', tone: 'text-az-600' },
    platform: { label: 'Platform', tone: 'text-ink-500' },
    people: { label: 'People', tone: 'text-warn-700' },
  }

  return (
    <div className="grid grid-cols-[300px_1fr] gap-5">
      {/* Step timeline */}
      <Card title="Fifteen steps" subtitle="Notification to a signed outcome" dense pad={false}>
        <div className="py-1">
          {steps.map((s) => {
            const state = stepState[s.id]
            const tone =
              state?.status === 'done'
                ? 'ok'
                : state?.status === 'blocked'
                  ? 'stop'
                  : state?.status === 'downgraded'
                    ? 'warn'
                    : state?.status === 'running'
                      ? 'blue'
                      : 'ghost'
            const active = selectedStep === s.id
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => onSelectStep(active ? null : s.id)}
                className={`w-full text-left px-4 py-2 flex items-start gap-2.5 border-l-2 transition-colors ${
                  active
                    ? 'border-az-700 bg-az-50'
                    : 'border-transparent hover:bg-ink-50'
                }`}
              >
                <span className="shrink-0 mt-[5px]">
                  <Dot tone={tone as never} pulse={state?.status === 'running'} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline gap-1.5">
                    <span className="font-mono text-[10px] text-ink-400 tabular">
                      {String(s.no).padStart(2, '0')}
                    </span>
                    <span
                      className={`text-[12px] ${
                        state ? 'text-ink-800 font-medium' : 'text-ink-500'
                      }`}
                    >
                      {s.title}
                    </span>
                  </span>
                  <span className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                    <span className={`text-[10px] ${lanes[s.lane]?.tone ?? 'text-ink-400'}`}>
                      {lanes[s.lane]?.label}
                    </span>
                    {s.pillar && <PillarChip pillar={s.pillar} compact />}
                    {state?.ms !== undefined && (
                      <span className="text-[10px] text-ink-400 tabular">{ms(state.ms)}</span>
                    )}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      </Card>

      {/* Event feed + summary */}
      <div className="space-y-5">
        {summary && (
          <Card dense>
            <div className="grid grid-cols-7 gap-5">
              <Stat
                label="Outcome"
                value={summary.outcome as string}
                tone={decisionTone(summary.outcome as string)}
                mono={false}
              />
              <Stat label="Duration" value={ms(summary.duration_ms as number)} />
              <Stat label="Tool calls" value={num(summary.tool_calls as number)} />
              <Stat label="Tokens" value={num(summary.total_tokens as number)} />
              <Stat
                label="Cost"
                value={eur(summary.cost_eur as number, 4)}
                sub={summary.cost_basis as string}
              />
              <Stat
                label="Security events"
                value={num(summary.security_events as number)}
                tone={(summary.security_events as number) > 0 ? 'warn' : 'ok'}
              />
              <Stat
                label="Served by"
                value={
                  summary.runtime === 'deterministic' ? 'Rules only' : 'Assistant'
                }
                tone={summary.runtime === 'deterministic' ? 'ghost' : 'ok'}
                mono={false}
                sub={
                  <>
                    {(summary.throttle_wait_ms as number) > 0 && (
                      <div className="text-ink-400">
                        waited {ms(summary.throttle_wait_ms as number)} on capacity
                      </div>
                    )}
                  </>
                }
              />
            </div>
            {guardEvent && (
              <div className="mt-4 pt-4 border-t border-ink-100 flex items-start gap-3">
                <Badge tone={guardEvent.status === 'ok' ? 'ok' : 'warn'}>
                  {guardEvent.status === 'ok' ? 'guard passed' : 'guard downgraded'}
                </Badge>
                <p className="text-[12.5px] text-ink-600 leading-snug">{guardEvent.detail}</p>
              </div>
            )}
          </Card>
        )}

        {runEnd?.status === 'failed' && (
          <Card title="The run stopped" dense>
            <div className="border border-stop-100 bg-stop-100 rounded px-3.5 py-3">
              <p className="text-[12.5px] text-stop-700 leading-snug">{runEnd.detail}</p>
              {runEnd.data?.remedy ? (
                <p className="text-[12px] text-stop-700 mt-2 leading-snug">
                  {runEnd.data.remedy as string}
                </p>
              ) : null}
              <div className="text-[11px] text-stop-700 mt-2">
                Completed {String(runEnd.data?.completed_steps ?? 0)} step(s) and{' '}
                {String(runEnd.data?.tool_calls ?? 0)} tool call(s) before stopping. Nothing
                partial was written.
              </div>
            </div>
          </Card>
        )}

        <Card
          title={selectedStep ? `Trace · ${selectedStep}` : 'Trace'}
          subtitle={
            selectedStep
              ? 'Filtered to one step — click it again to see everything'
              : 'Every tool call, every control, in the order it happened'
          }
          right={
            <div className="flex items-center gap-2">
              {running && (
                <span className="flex items-center gap-1.5 text-[11.5px] text-az-700">
                  <Dot tone="blue" pulse /> streaming
                </span>
              )}
              <Badge tone="ghost">{events.length} events</Badge>
            </div>
          }
          pad={false}
          dense
        >
          {allEvents.length === 0 ? (
            <div className="p-8 text-center">
              <p className="text-[13px] text-ink-600 mb-1">
                {t('cw2.notWorked')}
              </p>
              <p className="text-[12px] text-ink-500 max-w-md mx-auto">
                {t('cw2.startsOnOwn')}
              </p>
            </div>
          ) : (
            <div ref={feedRef} className="max-h-[560px] overflow-y-auto">
              {events.map((ev) => (
                <EventRow
                  key={ev.seq}
                  ev={ev}
                  open={expanded.has(ev.seq)}
                  onToggle={() => onToggle(ev.seq)}
                />
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

function EventRow({
  ev, open, onToggle,
}: { ev: TraceEvent; open: boolean; onToggle: () => void }) {
  const tone =
    ev.status === 'blocked'
      ? 'stop'
      : ev.status === 'downgraded'
        ? 'warn'
        : ev.kind === 'security'
          ? 'stop'
          : ev.kind === 'sign' || ev.kind === 'write'
            ? 'blue'
            : ev.kind === 'guard'
              ? 'blue'
              : 'neutral'
  const hasData = ev.data && Object.keys(ev.data).length > 0

  return (
    <div className="border-b border-ink-100 last:border-0 fade-up">
      <button
        type="button"
        onClick={onToggle}
        disabled={!hasData}
        className="w-full text-left px-4 py-2 flex items-start gap-3 hover:bg-ink-50/70 disabled:hover:bg-transparent"
      >
        <span className="font-mono text-[10px] text-ink-300 tabular mt-[3px] w-6 shrink-0">
          {String(ev.seq).padStart(2, '0')}
        </span>
        <span className="shrink-0 mt-[3px]">
          <Dot tone={tone as never} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2 flex-wrap">
            <span className="text-[10.5px] font-semibold uppercase tracking-[0.05em] text-ink-500">
              {KIND_LABEL[ev.kind] ?? ev.kind}
            </span>
            {ev.agent && (
              <span className="text-[11px] font-medium text-az-700">{ev.agent}</span>
            )}
            {ev.pillar && <PillarChip pillar={ev.pillar} compact />}
            {ev.data?.risk_class ? (
              <Badge tone="ghost" mono>
                {ev.data.risk_class as string}
              </Badge>
            ) : null}
            <span className="ml-auto text-[10px] text-ink-400 tabular">{ms(ev.elapsed_ms)}</span>
          </span>
          <span className="block text-[12.5px] text-ink-700 mt-0.5 leading-snug">
            {ev.detail}
          </span>
          {ev.kind === 'tool_call' && ev.data?.args &&
            Object.keys(ev.data.args as Json).length > 0 && (
              <span className="block mt-1">
                <Mono>{JSON.stringify(ev.data.args)}</Mono>
              </span>
            )}
        </span>
        {hasData && (
          <span className="text-ink-300 text-[11px] shrink-0 mt-[3px]">{open ? '−' : '+'}</span>
        )}
      </button>
      {open && hasData && (
        <div className="px-4 pb-3 pl-[52px]">
          <EventDetail ev={ev} />
        </div>
      )}
    </div>
  )
}

function EventDetail({ ev }: { ev: TraceEvent }) {
  const d = ev.data as Json

  if (ev.kind === 'guard' && d.firewall) {
    const fw = d.firewall as Json
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap gap-3 text-[11.5px]">
          <span className="text-ink-500">
            verdict <Badge tone={fw.passed ? 'ok' : 'stop'}>{fw.action as string}</Badge>
          </span>
          <span className="text-ink-500">
            risk <span className="tabular text-ink-800">{(fw.risk_score as number).toFixed(2)}</span>
          </span>
          <span className="text-ink-500">
            pack <Mono>{fw.rule_pack_version as string}</Mono>
          </span>
        </div>
        {(fw.violations as Json[]).length === 0 ? (
          <p className="text-[12px] text-ink-600">
            All eight inbound attack classes screened, nothing fired.
          </p>
        ) : (
          <ul>
            {(fw.violations as Json[]).map((v, i) => (
              <CheckRow
                key={i}
                passed={false}
                id={v.rule_id as string}
                label={v.attack_class as string}
                detail={`${v.detail as string} Matched: “${v.matched as string}”`}
              />
            ))}
          </ul>
        )}
      </div>
    )
  }

  if (ev.kind === 'guard' && d.guard) {
    const g = d.guard as Json
    return (
      <div>
        <div className="flex flex-wrap gap-3 text-[11.5px] mb-2">
          <span className="text-ink-500">
            proposed{' '}
            <Badge tone={decisionTone(d.proposed_decision as string)}>
              {(d.proposed_decision as string) || '—'}
            </Badge>
          </span>
          <span className="text-ink-500">
            final{' '}
            <Badge tone={decisionTone(d.final_decision as string)}>
              {d.final_decision as string}
            </Badge>
          </span>
          <span className="text-ink-500">
            guard <Mono>{g.policy_guard_version as string}</Mono>
          </span>
        </div>
        <ul>
          {(g.checks as Json[]).map((c) => (
            <CheckRow
              key={c.check_id as string}
              passed={c.passed as boolean}
              id={c.check_id as string}
              label={c.name as string}
              detail={c.detail as string}
            />
          ))}
        </ul>
      </div>
    )
  }

  if (ev.kind === 'preflight') {
    return (
      <Table head={['Item', 'Type', 'Quality', 'Action', 'Verdict', 'Checks']}>
        {(d.items as Json[]).map((i) => (
          <tr key={i.doc_id as string}>
            <Td mono>{i.filename as string}</Td>
            <Td>{i.doc_type as string}</Td>
            <Td align="right">{(i.quality_score as number).toFixed(2)}</Td>
            <Td>
              <Badge tone={i.quality_action === 'accept' ? 'ok' : 'warn'}>
                {i.quality_action as string}
              </Badge>
            </Td>
            <Td>
              <Badge tone={statusTone(i.verdict as string)}>{i.verdict as string}</Badge>
            </Td>
            <Td>
              <span className="text-[11px] text-ink-500">
                {(i.checks as Json[]).filter((c) => c.passed).length}/
                {(i.checks as Json[]).length} passed
              </span>
            </Td>
          </tr>
        ))}
      </Table>
    )
  }

  if (ev.kind === 'sign') {
    const e = d.envelope as Json
    return (
      <div className="space-y-2">
        <KeyValueGrid cols={4}>
          <Field label="Action" mono>{e.action as string}</Field>
          <Field label="Nonce" mono>{String(e.nonce)}</Field>
          <Field label="Signer" mono>{e.signer as string}</Field>
          <Field label="Policy version" mono>{e.policy_version as string}</Field>
          <Field label="Agent identity" mono>{e.agent_id as string}</Field>
          <Field label="Service identity" mono>{e.service_identity as string}</Field>
          <Field label="Payload hash" mono>{shortHash(e.payload_hash as string, 16)}</Field>
          <Field label="Chain hash" mono>{shortHash(e.chain_hash as string, 16)}</Field>
        </KeyValueGrid>
        <p className="text-[11.5px] text-ink-500">
          Previous entry: <Mono>{shortHash(e.prev_hash as string, 16)}</Mono> — each envelope
          is linked to the one before it, so removing or reordering an entry is visible.
        </p>
      </div>
    )
  }

  if (ev.kind === 'write') {
    const g = d.gateway as Json
    return (
      <div>
        <ul>
          {(g.checks as Json[]).map((c, i) => (
            <CheckRow
              key={i}
              passed={c.passed as boolean}
              label={(c.check as string).replace(/_/g, ' ')}
              detail={c.detail as string}
            />
          ))}
        </ul>
        {g.committed_ref ? (
          <p className="text-[11.5px] text-ink-500 mt-2">
            Committed once as <Mono>{g.committed_ref as string}</Mono>
            {g.idempotent_replay ? ' — this was a reconciled retry, not a second write.' : '.'}
          </p>
        ) : null}
      </div>
    )
  }

  if (ev.kind === 'tool_result' && d.zero_trust) {
    const zt = d.zero_trust as Json
    return (
      <div className="space-y-2">
        <div className="border border-stop-100 bg-stop-100 rounded p-3">
          <div className="text-[12px] font-medium text-stop-700 mb-1">
            Retrieved content sanitised
          </div>
          <p className="text-[11.5px] text-stop-700 leading-snug">{zt.note as string}</p>
        </div>
        {(zt.findings as Json[]).map((f, i) => (
          <div key={i} className="text-[11.5px] text-ink-600">
            <Mono>{f.path as string}</Mono> · {(f.attack_classes as string[]).join(', ')} ·
            removed <span className="text-stop-700">“{(f.removed as string[])[0]}”</span>
          </div>
        ))}
        <JsonBlock value={d.result} maxHeight={200} />
      </div>
    )
  }

  if (ev.kind === 'security') {
    return (
      <div className="border border-stop-100 bg-stop-100 rounded p-3 space-y-1.5">
        <div className="flex gap-2 items-center">
          <Badge tone="stop">{d.kind as string}</Badge>
          <Badge tone="ghost">{d.severity as string}</Badge>
          {(d.rule_ids as string[])?.map((r) => (
            <Mono key={r}>{r}</Mono>
          ))}
        </div>
        <p className="text-[12px] text-stop-700 leading-snug">{d.detail as string}</p>
      </div>
    )
  }

  return <JsonBlock value={d.output ?? d.result ?? d} />
}

/* ── Evidence ────────────────────────────────────────────────────────── */

function EvidencePanel({ documents }: { documents: Json[] }) {
  const [open, setOpen] = useState<string | null>(documents[0]?.doc_id as string ?? null)
  if (documents.length === 0) return <Empty>No evidence on this claim.</Empty>

  return (
    <div className="grid grid-cols-[300px_1fr] gap-5">
      <Card title="Evidence" subtitle={`${documents.length} items received`} dense pad={false}>
        <div className="py-1">
          {documents.map((d) => (
            <button
              key={d.doc_id as string}
              type="button"
              onClick={() => setOpen(d.doc_id as string)}
              className={`w-full text-left px-4 py-2.5 border-l-2 transition-colors ${
                open === d.doc_id
                  ? 'border-az-700 bg-az-50'
                  : 'border-transparent hover:bg-ink-50'
              }`}
            >
              <div className="text-[12px] font-medium text-ink-800 truncate">
                {d.filename as string}
              </div>
              <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                <Badge tone="ghost">{d.doc_type as string}</Badge>
                <Badge
                  tone={
                    (d.quality_score as number) >= 0.85
                      ? 'ok'
                      : (d.quality_score as number) >= 0.55
                        ? 'warn'
                        : 'stop'
                  }
                >
                  q {(d.quality_score as number).toFixed(2)}
                </Badge>
                {(d.fields as Json[]).length > 0 && (
                  <span className="text-[10.5px] text-ink-400">
                    {(d.fields as Json[]).length} fields
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      </Card>

      {(() => {
        const doc = documents.find((d) => d.doc_id === open)
        if (!doc) return <Empty>Select an item.</Empty>
        const injected = /<!--|SYSTEM\s*:/i.test((doc.ocr_text as string) ?? '')
        return (
          <div className="space-y-5">
            <Card title={doc.filename as string} subtitle={`${doc.doc_id as string}`} dense>
              <KeyValueGrid cols={4}>
                <Field label="Kind">{doc.kind as string}</Field>
                <Field label="MIME" mono>{doc.mime_type as string}</Field>
                <Field label="Size">{num((doc.size_bytes as number) / 1024, 0)} KB</Field>
                <Field label="Pages">{String(doc.page_count)}</Field>
                <Field label="Scan">
                  <Badge tone={statusTone(doc.scan_verdict as string)}>
                    {doc.scan_verdict as string}
                  </Badge>
                </Field>
                <Field label="Quality action">
                  <Badge tone={doc.quality_action === 'accept' ? 'ok' : 'warn'}>
                    {doc.quality_action as string}
                  </Badge>
                </Field>
                <Field label="SHA-256" mono>{shortHash(doc.sha256 as string, 14)}</Field>
                <Field label="Received">{when(doc.uploaded_at as string)}</Field>
              </KeyValueGrid>
              {(doc.preflight_notes as string[])?.length > 0 && (
                <div className="mt-4 pt-4 border-t border-ink-100">
                  {(doc.preflight_notes as string[]).map((n, i) => (
                    <p key={i} className="text-[12px] text-warn-700">
                      {n}
                    </p>
                  ))}
                </div>
              )}
            </Card>

            {(doc.fields as Json[]).length > 0 && (
              <Card
                title="Extraction"
                subtitle="Every field carries its own confidence. Extracted is never silently promoted to validated."
                dense
              >
                <Table head={['Field', 'Read as', 'Confidence', 'Validated', 'Recovery']}>
                  {(doc.fields as Json[]).map((f) => (
                    <tr key={f.field_name as string}>
                      <Td>{(f.field_name as string).replace(/_/g, ' ')}</Td>
                      <Td mono>{f.extracted_value as string}</Td>
                      <Td align="right">
                        <div className="flex items-center gap-2 justify-end">
                          <span className="tabular">{(f.confidence as number).toFixed(2)}</span>
                          <div className="w-12">
                            <Meter
                              value={f.confidence as number}
                              height={4}
                              tone={
                                (f.confidence as number) >= 0.85
                                  ? 'ok'
                                  : (f.confidence as number) >= 0.65
                                    ? 'warn'
                                    : 'stop'
                              }
                            />
                          </div>
                        </div>
                      </Td>
                      <Td mono>
                        {f.validated_value ? (
                          (f.validated_value as string)
                        ) : (
                          <span className="text-ink-400 font-sans">not yet</span>
                        )}
                      </Td>
                      <Td>
                        <Badge tone={f.recovery_action === 'accept' ? 'ok' : 'warn'}>
                          {f.recovery_action as string}
                        </Badge>
                      </Td>
                    </tr>
                  ))}
                </Table>
              </Card>
            )}

            {(doc.detections as Json[])?.length > 0 && (
              <Card title="Photo findings" dense>
                <Table head={['Panel', 'Action', 'Paint', 'Confidence']}>
                  {(doc.detections as Json[]).map((det, i) => (
                    <tr key={i}>
                      <Td mono>{det.panel as string}</Td>
                      <Td>{det.action as string}</Td>
                      <Td>{det.paint ? 'yes' : 'no'}</Td>
                      <Td align="right">{(det.confidence as number).toFixed(2)}</Td>
                    </tr>
                  ))}
                </Table>
              </Card>
            )}

            {doc.ocr_text ? (
              <Card
                title="Document text, as received"
                subtitle={
                  injected
                    ? 'This file carries an instruction block. It is stored verbatim as evidence, and stripped in transit before any model sees it.'
                    : 'Stored verbatim. Screened on every read.'
                }
                dense
              >
                <pre className="font-mono text-[11.5px] leading-[1.6] text-ink-700 bg-ink-50 border border-ink-200 rounded p-3 overflow-x-auto whitespace-pre-wrap">
                  {(doc.ocr_text as string)
                    .split(/(<!--[\s\S]*?-->)/)
                    .map((part, i) =>
                      part.startsWith('<!--') ? (
                        <mark
                          key={i}
                          className="bg-stop-100 text-stop-700 px-1 rounded not-italic"
                        >
                          {part}
                        </mark>
                      ) : (
                        <span key={i}>{part}</span>
                      ),
                    )}
                </pre>
                {injected && (
                  <p className="text-[11.5px] text-stop-700 mt-2.5 leading-snug">
                    The highlighted block is the attack. The customer did not write it — it
                    arrived inside the repair quote. Rule ZT-INJ-009 strips it on every read,
                    and the claim continues on the inert remainder.
                  </p>
                )}
              </Card>
            ) : null}
          </div>
        )
      })()}
    </div>
  )
}

/* ── Assessment ──────────────────────────────────────────────────────── */

function AssessmentPanel({
  coverage, estimate, risk, events,
}: { coverage: Json | null; estimate: Json | null; risk: Json; events: TraceEvent[] }) {
  const damage = events.find((e) => e.step_id === 'damage.assess' && e.kind === 'agent_output')
    ?.data?.output as Json | undefined
  const graph = events.find((e) => e.kind === 'tool_result' && e.data?.tool === 'graph_neighbours')
    ?.data?.result as Json | undefined

  if (!coverage && !estimate) {
    return <Empty>Nothing has been assessed on this claim yet.</Empty>
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-5">
        {coverage && (
          <Card title="Coverage" subtitle="Grounded on the policy wording, always cited" dense>
            <div className="flex items-center gap-2 mb-3">
              <Badge
                tone={
                  (coverage.status as string).startsWith('covered')
                    ? 'ok'
                    : coverage.status === 'unknown'
                      ? 'warn'
                      : 'stop'
                }
              >
                {(coverage.status as string).replace(/_/g, ' ')}
              </Badge>
              <span className="text-[12px] text-ink-500">
                excess {eur(coverage.excess_eur as number)}
              </span>
              <span className="text-[12px] text-ink-500 ml-auto tabular">
                confidence {(coverage.confidence as number).toFixed(2)}
              </span>
            </div>
            <p className="text-[12.5px] text-ink-700 leading-relaxed mb-4">
              {coverage.reasoning as string}
            </p>
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-500 mb-2">
              Clauses relied on
            </div>
            <div className="space-y-2.5">
              {(coverage.citations as Json[]).map((c) => (
                <div
                  key={c.clause_id as string}
                  className="border-l-2 border-az-300 pl-3 py-0.5"
                >
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <Mono className="text-az-700 font-medium">{c.clause_id as string}</Mono>
                    <span className="text-[11.5px] text-ink-700">{c.title as string}</span>
                    <span className="text-[10.5px] text-ink-400">
                      {c.section as string} · p.{String(c.page)}
                    </span>
                  </div>
                  <p className="text-[11.5px] text-ink-600 mt-1 leading-snug italic">
                    “{c.quote as string}”
                  </p>
                </div>
              ))}
              {(coverage.citations as Json[]).length === 0 && (
                <p className="text-[12px] text-warn-700">
                  No authoritative clause was retrieved. The agent abstained rather than
                  answering from general knowledge.
                </p>
              )}
            </div>
          </Card>
        )}

        {estimate && (
          <Card
            title="Repair estimate"
            subtitle="Computed inside the managed sandbox"
            dense
            right={<PillarChip pillar={2} compact />}
          >
            <Table head={['Line', 'Action', 'Parts', 'Hours']}>
              {(estimate.items as Json[]).map((it, i) => (
                <tr key={i}>
                  <Td mono>{(it.part as string).replace(/_/g, ' ')}</Td>
                  <Td>{it.action as string}</Td>
                  <Td align="right">{eur(it.part_price_eur as number)}</Td>
                  <Td align="right">{num(it.labour_hours as number, 1)}</Td>
                </tr>
              ))}
            </Table>
            <div className="mt-4 pt-3 border-t border-ink-200 space-y-1.5 text-[12.5px]">
              <Row label={`Parts`} value={eur(estimate.total_parts as number)} />
              <Row
                label={`Labour · ${num(estimate.labour_hours as number, 1)} h at ${eur(
                  estimate.labour_rate_eur as number,
                )}/h`}
                value={eur(estimate.total_labour as number)}
              />
              <Row label="VAT 20%" value={eur(estimate.total_tax as number)} />
              <div className="pt-2 border-t border-ink-200">
                <Row
                  label="Total"
                  value={eur(estimate.total_cost as number)}
                  bold
                />
              </div>
            </div>
            {estimate.reasonableness_band ? (
              <div className="mt-3">
                <Badge
                  tone={
                    (estimate.reasonableness_band as string).includes('within') ? 'ok' : 'warn'
                  }
                >
                  {estimate.reasonableness_band as string}
                </Badge>
              </div>
            ) : null}
            {estimate.sandbox_telemetry &&
              Object.keys(estimate.sandbox_telemetry as Json).length > 0 && (
                <div className="mt-4 pt-3 border-t border-ink-100">
                  <div className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-500 mb-2">
                    Isolation telemetry
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
                    {Object.entries(estimate.sandbox_telemetry as Json)
                      .filter(([k]) => k !== 'inspector_version')
                      .map(([k, v]) => (
                        <div key={k} className="flex justify-between gap-2">
                          <span className="text-ink-500 truncate">{k.replace(/_/g, ' ')}</span>
                          <Mono className="text-ink-800">{String(v)}</Mono>
                        </div>
                      ))}
                  </div>
                  <p className="text-[11px] text-ink-500 mt-2.5 leading-snug">
                    Proof of isolation, emitted by the execution itself — not an assertion
                    that it was supposed to be isolated.
                  </p>
                </div>
              )}
          </Card>
        )}
      </div>

      <div className="grid grid-cols-2 gap-5">
        {damage && (
          <Card title="Damage assessment" dense>
            <div className="flex items-center gap-2 mb-3">
              <Badge tone={damage.severity === 'complex' ? 'warn' : 'neutral'}>
                {damage.severity as string}
              </Badge>
              {damage.structural_damage ? <Badge tone="stop">structural</Badge> : null}
              <span className="text-[12px] text-ink-500 ml-auto">
                {String(damage.panel_count)} panels
              </span>
            </div>
            <p className="text-[12.5px] text-ink-600 mb-3">{damage.severity_basis as string}</p>
            <Table head={['Panel', 'Action', 'Structural', 'Confidence']}>
              {(damage.panels as Json[]).map((p, i) => (
                <tr key={i}>
                  <Td mono>{(p.panel as string).replace(/_/g, ' ')}</Td>
                  <Td>{p.action as string}</Td>
                  <Td>{p.structural ? <Badge tone="stop">yes</Badge> : 'no'}</Td>
                  <Td align="right">{(p.confidence as number).toFixed(2)}</Td>
                </tr>
              ))}
            </Table>
            {(damage.low_quality_photos as Json[])?.length > 0 && (
              <p className="text-[12px] text-warn-700 mt-3">
                {(damage.low_quality_photos as Json[]).length} photo(s) too poor to read — a
                specific replacement view has been requested.
              </p>
            )}
          </Card>
        )}

        <Card title="Risk signals" subtitle="Signals, not findings" dense>
          <div className="flex items-baseline gap-3 mb-3">
            <Stat
              label="Composite score"
              value={(risk.score as number).toFixed(2)}
              tone={(risk.score as number) > 0.55 ? 'stop' : 'ok'}
            />
            <div className="flex-1 mt-3">
              <Meter
                value={risk.score as number}
                tone={(risk.score as number) > 0.55 ? 'stop' : 'ok'}
              />
              <div className="text-[10.5px] text-ink-400 mt-1">
                autonomy threshold 0.55
              </div>
            </div>
          </div>
          {(risk.signals as Json[]).length === 0 ? (
            <p className="text-[12.5px] text-ink-500">No signals recorded on this claim.</p>
          ) : (
            <div className="space-y-2.5">
              {(risk.signals as Json[]).map((s, i) => (
                <div key={i} className="flex gap-2.5">
                  <Badge tone="ghost" mono>
                    {(s.weight as number).toFixed(2)}
                  </Badge>
                  <div className="min-w-0">
                    <div className="text-[11.5px] font-medium text-ink-700">
                      {(s.signal_type as string).replace(/_/g, ' ')}
                    </div>
                    <p className="text-[11.5px] text-ink-600 leading-snug">
                      {s.detail as string}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
          {graph?.neighbours ? (
            <div className="mt-4 pt-4 border-t border-ink-100">
              <div className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-500 mb-2">
                Graph neighbourhood
              </div>
              <div className="space-y-1.5">
                {(graph.neighbours as Json[]).slice(0, 8).map((n, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11.5px]">
                    {n.flagged ? <Dot tone="stop" /> : <Dot tone="ghost" />}
                    <Mono>{n.node_id as string}</Mono>
                    <span className="text-ink-500">{(n.edge as string).replace(/_/g, ' ')}</span>
                    <span className="text-ink-400 ml-auto">d{String(n.distance)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </Card>
      </div>
    </div>
  )
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <span className={bold ? 'font-semibold text-ink-800' : 'text-ink-600'}>{label}</span>
      <span className={`tabular ${bold ? 'font-semibold text-ink-900' : 'text-ink-800'}`}>
        {value}
      </span>
    </div>
  )
}

/* ── Decision & guard ────────────────────────────────────────────────── */

function DecisionPanel({
  guardEvent, runEnd, tasks,
}: { guardEvent?: TraceEvent; runEnd?: TraceEvent; tasks: Json[] }) {
  if (!guardEvent) {
    return <Empty>No decision has reached the policy checks on this claim yet.</Empty>
  }
  const g = guardEvent.data.guard as Json
  const routing = runEnd?.data?.routing as Json | undefined
  const final = runEnd?.data?.final as Json | undefined

  return (
    <div className="grid grid-cols-[1fr_360px] gap-5">
      <Card
        title="Deterministic policy guard"
        subtitle="Applied after the model has spoken. The rules live in versioned code outside the prompt, so changing a prompt cannot change what the business allows."
        right={<PillarChip pillar={1} compact />}
      >
        <div className="flex items-center gap-4 mb-4 pb-4 border-b border-ink-100">
          <div>
            <div className="text-[10.5px] uppercase tracking-[0.06em] text-ink-500 mb-1">
              Agent proposed
            </div>
            <Badge tone={decisionTone(g.original_decision as string)}>
              {(g.original_decision as string) || '—'}
            </Badge>
          </div>
          <span className="text-ink-300 text-lg">→</span>
          <div>
            <div className="text-[10.5px] uppercase tracking-[0.06em] text-ink-500 mb-1">
              Guard decided
            </div>
            <Badge tone={decisionTone((final?.decision as string) ?? '')}>
              {(final?.decision as string) ?? '—'}
            </Badge>
          </div>
          <div className="ml-auto text-right">
            <div className="text-[10.5px] uppercase tracking-[0.06em] text-ink-500 mb-1">
              Ceiling in force
            </div>
            <span className="text-[13px] font-semibold tabular text-ink-800">
              {eur(g.auto_approval_ceiling_eur as number, 0)}
            </span>
          </div>
        </div>
        <ul>
          {(g.checks as Json[]).map((c) => (
            <CheckRow
              key={c.check_id as string}
              passed={c.passed as boolean}
              id={c.check_id as string}
              label={c.name as string}
              detail={c.detail as string}
            />
          ))}
        </ul>
        <p className="text-[12px] text-ink-600 mt-4 leading-relaxed">{g.reasoning as string}</p>
      </Card>

      <div className="space-y-5">
        {routing && (
          <Card title="Routing" dense>
            {routing.needs_human ? (
              <>
                <KeyValueGrid cols={1}>
                  <Field label="Queue">{routing.queue as string}</Field>
                  <Field label="Reason">{(routing.reason as string).replace(/_/g, ' ')}</Field>
                  <Field label="Authority required">
                    {(routing.authority_required as string) ?? '—'}
                  </Field>
                  <Field label="Failed checks" mono>
                    {(routing.failed_checks as string[]).join(', ') || '—'}
                  </Field>
                </KeyValueGrid>
                <p className="text-[12px] text-ink-600 mt-3 leading-snug">
                  {routing.reason_detail as string}
                </p>
              </>
            ) : (
              <div className="text-[12.5px] text-ok-700">
                No human touch required — every deterministic check passed inside the
                autonomous limit.
              </div>
            )}
          </Card>
        )}

        {tasks.length > 0 && (
          <Card title="Review tasks" dense>
            <div className="space-y-3">
              {tasks.map((t) => (
                <div key={t.task_id as string} className="border-b border-ink-100 pb-3 last:border-0 last:pb-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Mono>{t.task_id as string}</Mono>
                    <Badge tone={t.status === 'resolved' ? 'ok' : 'warn'}>
                      {t.status as string}
                    </Badge>
                    <Badge tone="ghost">{t.queue as string}</Badge>
                  </div>
                  <p className="text-[12px] text-ink-600 mt-1.5 leading-snug">
                    {t.reason_detail as string}
                  </p>
                  {t.decision ? (
                    <p className="text-[11.5px] text-ink-500 mt-1.5">
                      {t.decision as string} by {t.resolved_by as string}
                      {t.approval_ref ? (
                        <>
                          {' · '}
                          <Mono>{t.approval_ref as string}</Mono>
                        </>
                      ) : null}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}

/* ── Customer ────────────────────────────────────────────────────────── */

function CustomerPanel({ messages, timeline }: { messages: Json[]; timeline: Json[] }) {
  return (
    <div className="grid grid-cols-[1fr_340px] gap-5">
      <Card
        title="What the customer is told"
        subtitle="Approved templates only, in their own language, with the outbound guard applied"
      >
        {messages.length === 0 ? (
          <Empty>No message has been drafted yet.</Empty>
        ) : (
          <div className="space-y-5">
            {messages.map((m) => (
              <div key={m.message_id as string}>
                <div className="flex items-center gap-2 mb-2.5 flex-wrap">
                  <Badge tone={m.status === 'drafted' ? 'ok' : 'stop'}>{m.status as string}</Badge>
                  <Badge tone="ghost">{(m.language as string).toUpperCase()}</Badge>
                  <span className="text-[11px] text-ink-400 ml-auto">
                    {when(m.created_at as string)}
                  </span>
                  {/* The whole message, subject line included, ready to paste. */}
                  <CopyButton
                    text={`${m.subject as string}\n\n${m.body as string}`}
                  />
                </div>
                <div className="border border-ink-200 rounded bg-ink-50/60 p-4">
                  <div className="text-[13px] font-semibold text-ink-900 mb-2.5">
                    {m.subject as string}
                  </div>
                  {(m.body as string).split('\n\n').map((p, i) => (
                    <p key={i} className="text-[13px] text-ink-700 leading-relaxed mb-2.5 last:mb-0">
                      {p}
                    </p>
                  ))}
                </div>
                {(m.guard_findings as Json[])?.length > 0 && (
                  <div className="mt-2.5 border border-stop-100 bg-stop-100 rounded p-3">
                    <div className="text-[12px] font-medium text-stop-700 mb-1">
                      Withheld by the outbound guard
                    </div>
                    {(m.guard_findings as Json[]).map((f, i) => (
                      <p key={i} className="text-[11.5px] text-stop-700">
                        {f.detail as string}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ))}
            <p className="text-[11.5px] text-ink-500 leading-snug border-t border-ink-100 pt-3">
              The outbound guard screens every draft for internal rule identifiers, guard
              reasoning, queue names and investigation status, and refuses any figure above
              the approved settlement. A customer is never told that a claim is under
              investigation.
            </p>
          </div>
        )}
      </Card>

      <Card title="Claim timeline" dense>
        {timeline.length === 0 ? (
          <Empty>Nothing recorded yet.</Empty>
        ) : (
          <ol className="space-y-3">
            {timeline.map((t, i) => (
              <li key={i} className="flex gap-2.5">
                <span className="shrink-0 mt-[5px]">
                  <Dot tone={i === timeline.length - 1 ? 'blue' : 'ghost'} />
                </span>
                <div className="min-w-0">
                  <div className="text-[12px] font-medium text-ink-800">
                    {(t.event as string).replace(/_/g, ' ')}
                  </div>
                  <p className="text-[11.5px] text-ink-600 leading-snug">{t.detail as string}</p>
                  <div className="text-[10.5px] text-ink-400 mt-0.5">{when(t.at as string)}</div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  )
}

/* ── Ledger ──────────────────────────────────────────────────────────── */

function LedgerPanel({ reference, events }: { reference: string; events: TraceEvent[] }) {
  const [ledger, setLedger] = useState<Json | null>(null)
  useEffect(() => {
    api.ledger().then(setLedger).catch(() => undefined)
  }, [events.length])

  if (!ledger) return <Spinner />
  const entries = (ledger.entries as Json[]).filter((e) => e.claim_id === reference)
  const chain = ledger.chain as Json

  return (
    <div className="space-y-5">
      <Card
        title="Signed actions on this claim"
        subtitle="Every passage through the Secure Write Gateway, hash-chained to the one before it"
        right={
          <Badge tone={chain.valid ? 'ok' : 'stop'}>
            {chain.valid ? 'chain verifies' : 'chain broken'}
          </Badge>
        }
      >
        {entries.length === 0 ? (
          <Empty>Nothing has been signed on this claim yet.</Empty>
        ) : (
          <div className="space-y-3">
            {entries.map((e) => (
              <div key={e.nonce as number} className="border border-ink-200 rounded p-4">
                <div className="flex items-center gap-2 mb-3 flex-wrap">
                  <Badge tone="blue" mono>
                    nonce {String(e.nonce)}
                  </Badge>
                  <Mono className="text-ink-800 font-medium">{e.action as string}</Mono>
                  <Badge tone="ghost">{e.agent_id as string}</Badge>
                  <Badge tone={e.verification_status === 'VERIFIED_AUTHENTIC' ? 'ok' : 'stop'}>
                    {e.verification_status as string}
                  </Badge>
                  <span className="text-[11px] text-ink-400 ml-auto">
                    {when(e.timestamp as string)}
                  </span>
                </div>
                <KeyValueGrid cols={4}>
                  <Field label="User" mono>{e.user_id as string}</Field>
                  <Field label="Policy version" mono>{e.policy_version as string}</Field>
                  <Field label="Approval" mono>{(e.approval_ref as string) || '—'}</Field>
                  <Field label="Signer" mono>{e.signer as string}</Field>
                  <Field label="Payload hash" mono>{shortHash(e.payload_hash as string, 14)}</Field>
                  <Field label="Previous" mono>{shortHash(e.prev_hash as string, 14)}</Field>
                  <Field label="Chain hash" mono>{shortHash(e.chain_hash as string, 14)}</Field>
                  <Field label="Signature" mono>{shortHash(e.signature as string, 14)}</Field>
                </KeyValueGrid>
                <details className="mt-3">
                  <summary className="text-[11.5px] text-az-700 cursor-pointer hover:underline">
                    Signed payload
                  </summary>
                  <div className="mt-2">
                    <JsonBlock value={e.payload} maxHeight={220} />
                  </div>
                </details>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
