import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import {
  Avatar, Button, Card, Chip, Empty, ErrorNote, Field, KeyValueGrid, Meter, Mono,
  Notice, PageHeader, Spinner, Stat, toneOf,
} from '../components/ui'
import { eur, num, when } from '../lib/format'
import type { Json, Persona, WorkTask } from '../types'

/** One queue view, framed for whoever is looking at it. */
const FRAMING: Record<string, { title: string; lede: string; empty: string }> = {
  work_queue: {
    title: 'My desk',
    lede: 'Claims the platform could not finish on its own. Each one says which check stopped it, so you are not guessing why it arrived.',
    empty: 'Nothing on your desk. Every claim the platform could finish, it finished.',
  },
  assessment_queue: {
    title: 'Assessments',
    lede: 'Damage, estimates and the repairability call. You own the technical position; the settlement is somebody else’s.',
    empty: 'No assessments waiting. Nothing has needed a technical opinion.',
  },
  approvals: {
    title: 'Approvals',
    lede: 'Decisions above handler authority. The agent’s recommendation is preserved next to what the guard did with it.',
    empty: 'Nothing waiting on your approval.',
  },
  investigations: {
    title: 'Investigations',
    lede: 'Referrals from handlers and from the platform’s own signals. Signals, not findings — the claim is frozen, not declined.',
    empty: 'No referrals open.',
  },
  recovery: {
    title: 'Recovery',
    lede: 'Settled claims where a third party may owe us — including the excess your customer is out of pocket for.',
    empty: 'Nothing to recover on at the moment.',
  },
}

export function WorkQueue({
  persona, feature, onOpenClaim, refreshKey,
}: {
  persona: Persona
  feature: string
  onOpenClaim: (ref: string) => void
  refreshKey: number
}) {
  const [data, setData] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .work(persona.key)
      .then((d) => {
        setData(d)
        const tasks = (d.tasks as WorkTask[]) ?? []
        setSelected((prev) => prev ?? tasks[0]?.task_id ?? null)
      })
      .catch((e: Error) => setError(e.message))
  }, [persona.key])

  useEffect(() => {
    setData(null)
    setSelected(null)
    load()
  }, [load, refreshKey])

  const frame = FRAMING[feature] ?? FRAMING.work_queue

  if (error) return <ErrorNote message={error} />
  if (!data) return <Spinner />

  const tasks = (data.tasks as WorkTask[]) ?? []
  const stages = (data.stages_owned as Json[]) ?? []
  const chosen = tasks.find((t) => t.task_id === selected) ?? null

  return (
    <>
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-2">
            <Avatar initials={persona.initials} accent={persona.accent} size={20} />
            {persona.role_label}
            <span className="text-ink-400">·</span>
            <span className="italic">{persona.role_de}</span>
          </span>
        }
        title={frame.title}
        lede={frame.lede}
        right={
          <>
            <Chip tone="ghost">
              {persona.authority_limit_eur > 0
                ? `Authority ${eur(persona.authority_limit_eur, 0)}`
                : 'No settlement authority'}
            </Chip>
            <Button variant="secondary" size="sm" onClick={load}>
              Refresh
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-4 gap-4 mb-5">
        <Card dense>
          <Stat label="Open" value={num(data.open as number)} tone={tasks.length ? 'warn' : 'ok'} />
        </Card>
        <Card dense>
          <Stat
            label="Value at stake"
            value={eur(data.value_at_stake_eur as number, 0)}
            tone="blue"
          />
        </Card>
        <Card dense>
          <Stat
            label="Past SLA"
            value={num(data.sla_breached as number)}
            tone={(data.sla_breached as number) > 0 ? 'stop' : 'ok'}
          />
        </Card>
        <Card dense>
          <Stat
            label="Within my authority"
            value={num(tasks.filter((t) => t.within_my_authority).length)}
            sub={
              persona.authority_limit_eur > 0
                ? `of ${tasks.length} waiting`
                : 'this role does not settle'
            }
          />
        </Card>
      </div>

      {tasks.length === 0 ? (
        <Card>
          <Empty>{frame.empty}</Empty>
        </Card>
      ) : (
        <div className="grid grid-cols-[minmax(340px,380px)_1fr] gap-5 items-start">
          <Card title="Prioritised" subtitle="Value, SLA, risk, failed automation" pad={false}>
            <div className="pb-2 max-h-[620px] overflow-y-auto">
              {tasks.map((t) => (
                <button
                  key={t.task_id}
                  type="button"
                  onClick={() => setSelected(t.task_id)}
                  className={`w-full text-left px-4 py-3.5 border-l-[3px] transition-colors ${
                    selected === t.task_id
                      ? 'border-az-700 bg-air/60'
                      : 'border-transparent hover:bg-ink-50'
                  }`}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <Mono className="text-ink-900">{t.claim_reference}</Mono>
                    <Chip tone={toneOf(t.status?.tone)}>{t.status?.label}</Chip>
                    {t.sla_breached && <Chip tone="stop">past SLA</Chip>}
                  </div>
                  <div className="text-[13px] text-ink-800 mt-1.5">
                    {t.reason.replace(/_/g, ' ')}
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-[11.5px] text-ink-500">{t.policyholder}</span>
                    <span className="text-[13px] tabular text-ink-900">
                      {t.proposed_amount_eur > 0 ? eur(t.proposed_amount_eur) : '—'}
                    </span>
                  </div>
                  {!t.within_my_authority && t.proposed_amount_eur > 0 && (
                    <div className="text-[11px] text-warn-700 mt-1">
                      needs {t.authority_required.replace(/_/g, ' ')}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </Card>

          {chosen ? (
            <TaskDetail
              task={chosen}
              persona={persona}
              onOpenClaim={onOpenClaim}
              onDecided={load}
            />
          ) : (
            <Card>
              <Empty>Select an item.</Empty>
            </Card>
          )}
        </div>
      )}

      {stages.length > 0 && (
        <Card
          className="mt-5"
          title="The stages you own"
          subtitle="Everything else on the claim belongs to somebody else, and the platform keeps it that way."
        >
          <div className="grid grid-cols-3 gap-4">
            {stages.map((s) => (
              <div key={s.id as string} className="bg-ink-50 rounded-xl p-4">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11.5px] text-ink-500">
                    {String(s.no).padStart(2, '0')}
                  </span>
                  <span className="text-[13px] text-ink-900">{s.title as string}</span>
                </div>
                <p className="text-[12px] text-ink-600 mt-1.5 leading-relaxed">
                  {s.summary as string}
                </p>
                {(s.exceptions as string[])?.length > 0 && (
                  <p className="text-[11.5px] text-warn-700 mt-2 leading-relaxed">
                    {(s.exceptions as string[])[0]}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  )
}

function TaskDetail({
  task, persona, onOpenClaim, onDecided,
}: {
  task: WorkTask
  persona: Persona
  onOpenClaim: (ref: string) => void
  onDecided: () => void
}) {
  const [detail, setDetail] = useState<Json | null>(null)
  const [outcome, setOutcome] = useState<Json | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [amount, setAmount] = useState(String(task.proposed_amount_eur ?? 0))
  const [note, setNote] = useState('')

  useEffect(() => {
    setDetail(null)
    setOutcome(null)
    setError(null)
    setAmount(String(task.proposed_amount_eur ?? 0))
    setNote('')
    api.reviewTask(task.task_id).then(setDetail).catch((e: Error) => setError(e.message))
  }, [task.task_id, task.proposed_amount_eur])

  const decide = async (decision: string) => {
    setBusy(true)
    setError(null)
    try {
      const body: Json = { decision, user_id: persona.user_id, note }
      if (decision === 'amend') body.amount_eur = Number(amount)
      setOutcome(await api.decideTask(task.task_id, body))
      onDecided()
      api.reviewTask(task.task_id).then(setDetail).catch(() => undefined)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const ws = (detail?.workspace as Json) ?? {}
  const coverage = ws.coverage as Json | null
  const estimates = (ws.estimates as Json[]) ?? []
  const risk = (ws.risk as Json) ?? {}
  const resolved = ((detail?.task as Json)?.status as string) === 'resolved'
  const canSettle = persona.authority_limit_eur > 0
  const withinAuthority = task.proposed_amount_eur <= persona.authority_limit_eur

  return (
    <div className="space-y-5">
      <Card
        title={`${task.claim_reference} · ${task.reason.replace(/_/g, ' ')}`}
        subtitle={task.reason_detail}
        right={
          <Button variant="secondary" size="sm" onClick={() => onOpenClaim(task.claim_reference)}>
            Open the claim
          </Button>
        }
      >
        <KeyValueGrid cols={5}>
          <Field label="Policyholder">{task.policyholder}</Field>
          <Field label="Agent proposed">
            <Chip tone="warn">{task.proposed_decision ?? '—'}</Chip>
          </Field>
          <Field label="Amount">{eur(task.proposed_amount_eur)}</Field>
          <Field label="Needs">{task.authority_required.replace(/_/g, ' ')}</Field>
          <Field label="Age">{num(task.age_minutes, 0)} min</Field>
        </KeyValueGrid>
        <div className="flex gap-2 mt-4 flex-wrap">
          {task.injury && <Chip tone="stop">injury reported</Chip>}
          {task.structural && <Chip tone="warn">structural</Chip>}
          {task.severity && <Chip tone="ghost">{task.severity}</Chip>}
        </div>
      </Card>

      {!detail ? (
        <Spinner />
      ) : (
        <>
          <div className="grid grid-cols-3 gap-4">
            <Card title="Cover" dense>
              {!coverage ? (
                <p className="text-[12.5px] text-ink-500">Not assessed.</p>
              ) : (
                <>
                  <Chip
                    tone={
                      String(coverage.status).startsWith('covered')
                        ? 'ok'
                        : coverage.status === 'unknown'
                          ? 'warn'
                          : 'stop'
                    }
                  >
                    {String(coverage.status).replace(/_/g, ' ')}
                  </Chip>
                  <p className="text-[12.5px] text-ink-600 mt-2.5 leading-relaxed">
                    {coverage.reasoning as string}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {((coverage.clauses_applied as string[]) ?? []).map((c) => (
                      <Chip key={c} tone="blue" mono>
                        {c}
                      </Chip>
                    ))}
                  </div>
                </>
              )}
            </Card>

            <Card title="Estimate" dense>
              {estimates.length === 0 ? (
                <p className="text-[12.5px] text-ink-500">No estimate yet.</p>
              ) : (
                (() => {
                  const e = estimates[estimates.length - 1]
                  return (
                    <>
                      <div className="text-[22px] tabular text-ink-900">
                        {eur(e.total_cost as number)}
                      </div>
                      <p className="text-[12px] text-ink-600 mt-1.5">
                        {eur(e.total_parts as number)} parts ·{' '}
                        {eur(e.total_labour as number)} labour ·{' '}
                        {eur(e.total_tax as number)} VAT
                      </p>
                      {e.reasonableness_band ? (
                        <Chip
                          tone={
                            String(e.reasonableness_band).includes('within') ? 'ok' : 'warn'
                          }
                          className="mt-2.5"
                        >
                          {e.reasonableness_band as string}
                        </Chip>
                      ) : null}
                    </>
                  )
                })()
              )}
            </Card>

            <Card title="Risk" dense>
              <div className="flex items-baseline gap-2.5">
                <span className="text-[22px] tabular text-ink-900">
                  {Number(risk.score ?? 0).toFixed(2)}
                </span>
                <span className="text-[12px] text-ink-500">threshold 0.55</span>
              </div>
              <div className="mt-2.5">
                <Meter
                  value={Number(risk.score ?? 0)}
                  over={Number(risk.score ?? 0) > 0.55}
                />
              </div>
              <div className="mt-3 space-y-2">
                {((risk.signals as Json[]) ?? []).slice(0, 3).map((s, i) => (
                  <p key={i} className="text-[11.5px] text-ink-600 leading-relaxed">
                    <span className="font-mono text-ink-500">
                      {Number(s.weight).toFixed(2)}
                    </span>{' '}
                    {s.detail as string}
                  </p>
                ))}
                {((risk.signals as Json[]) ?? []).length === 0 && (
                  <p className="text-[12.5px] text-ink-500">No signals.</p>
                )}
              </div>
            </Card>
          </div>

          <Card
            title="Decision"
            subtitle={
              resolved
                ? 'This task has been resolved.'
                : canSettle
                  ? 'Whatever you choose, the write is signed, verified at the gateway and written once.'
                  : `${persona.role_label} holds no settlement authority. You can record a technical position; the money is decided elsewhere.`
            }
          >
            {resolved ? (
              <div className="flex items-center gap-3 flex-wrap">
                <Chip tone="ok">{(detail.task as Json).decision as string}</Chip>
                <span className="text-[13px] text-ink-600">
                  by {(detail.task as Json).resolved_by as string} ·{' '}
                  {when((detail.task as Json).resolved_at as string)}
                </span>
                {(detail.task as Json).approval_ref ? (
                  <Mono className="text-ink-600">
                    {(detail.task as Json).approval_ref as string}
                  </Mono>
                ) : null}
              </div>
            ) : !canSettle ? (
              <Notice tone="blue" title="Not your call, by design">
                An investigator works the network and an assessor makes the technical call.
                Neither decides the money — that separation is the control, not an
                oversight. Refer it on when you are done.
              </Notice>
            ) : (
              <>
                {!withinAuthority && task.proposed_amount_eur > 0 && (
                  <div className="mb-4">
                    <Notice tone="stop" title="Above your authority">
                      {eur(task.proposed_amount_eur)} is above your limit of{' '}
                      {eur(persona.authority_limit_eur, 0)}. Approving will be refused
                      before anything is signed — the check is real, not a hidden button.
                    </Notice>
                  </div>
                )}
                <div className="flex items-end gap-4 flex-wrap">
                  <label className="block">
                    <span className="text-[12px] text-ink-600">Amount to settle</span>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[13px] text-ink-500">EUR</span>
                      <input
                        value={amount}
                        onChange={(e) => setAmount(e.target.value)}
                        className="w-36 bg-white border border-ink-300 rounded-xl px-3 py-2 text-[13.5px] font-mono tabular focus:outline-none focus:border-az-500 focus:ring-2 focus:ring-air"
                      />
                    </div>
                  </label>
                  <label className="flex-1 min-w-[280px] block">
                    <span className="text-[12px] text-ink-600">Note for the record</span>
                    <input
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="Why this decision"
                      className="mt-1 w-full bg-white border border-ink-300 rounded-xl px-3.5 py-2 text-[13px] focus:outline-none focus:border-az-500 focus:ring-2 focus:ring-air"
                    />
                  </label>
                </div>
                <div className="flex gap-2 mt-4 flex-wrap">
                  <Button onClick={() => decide('approve')} busy={busy}>
                    Approve {eur(task.proposed_amount_eur)}
                  </Button>
                  <Button variant="secondary" onClick={() => decide('amend')} busy={busy}>
                    Approve {eur(Number(amount) || 0)} instead
                  </Button>
                  <Button variant="secondary" onClick={() => decide('request_more')} busy={busy}>
                    Ask for more
                  </Button>
                  <Button variant="danger" onClick={() => decide('reject')} busy={busy}>
                    Reject
                  </Button>
                </div>
              </>
            )}
            {error && (
              <div className="mt-4">
                <ErrorNote message={error} />
              </div>
            )}
          </Card>

          {outcome && <Outcome outcome={outcome} />}
        </>
      )}
    </div>
  )
}

function Outcome({ outcome }: { outcome: Json }) {
  if (!outcome.accepted) {
    return (
      <Card title="Refused">
        <Notice tone="stop" title={String(outcome.reason).replace(/_/g, ' ')}>
          {eur(outcome.required_authority_eur as number)} requires more than the{' '}
          {eur(outcome.your_authority_eur as number, 0)} authority held. Nothing was signed
          and nothing was written.
        </Notice>
      </Card>
    )
  }
  const approver = outcome.approver as Json
  const audit = outcome.audit as Json
  return (
    <Card
      title="Written once, signed"
      subtitle="A human decision travels the same path as an autonomous one"
      right={<Chip tone="ok">{outcome.recorded_decision as string}</Chip>}
    >
      <KeyValueGrid cols={4}>
        <Field label="Approver">
          {approver.name as string}
          <div className="text-[11.5px] text-ink-500">{approver.role as string}</div>
        </Field>
        <Field label="Settled">{eur(outcome.settlement_amount_eur as number)}</Field>
        <Field label="Approval" mono>{(outcome.approval_ref as string) ?? '—'}</Field>
        <Field label="Row audit">
          <Chip tone={audit.healthy ? 'ok' : 'stop'}>
            {audit.healthy ? 'clean' : `${String(audit.tampered_count)} flagged`}
          </Chip>
        </Field>
      </KeyValueGrid>
      <ul className="mt-4">
        {((outcome.steps as Json[]) ?? []).map((s, i) => (
          <li key={i} className="flex gap-3 py-2 border-b border-ink-100 last:border-0">
            <span
              className={`shrink-0 mt-0.5 w-4 h-4 rounded-full grid place-items-center text-[10px] font-bold text-white ${
                s.passed ? 'bg-ok-600' : 'bg-stop-600'
              }`}
            >
              {s.passed ? '✓' : '!'}
            </span>
            <div>
              <div className="text-[13px] text-ink-900">
                {String(s.step).replace(/_/g, ' ')}
              </div>
              <p className="text-[12.5px] text-ink-600 leading-relaxed">
                {s.detail as string}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}
