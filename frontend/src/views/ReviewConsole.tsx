import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import {
  Badge, Button, Card, CheckRow, decisionTone, Empty, ErrorNote, Field, JsonBlock,
  KeyValueGrid, Meter, Mono, PageHeader, Spinner, Table, Td,
} from '../components/ui'
import { eur, num, when } from '../lib/format'
import type { Json, ReviewTask, Staff } from '../types'

export function ReviewConsole({ onOpenClaim }: { onOpenClaim: (ref: string) => void }) {
  const [queue, setQueue] = useState<Json | null>(null)
  const [staff, setStaff] = useState<Staff[]>([])
  const [actor, setActor] = useState('klaus.reiter')
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<Json | null>(null)
  const [outcome, setOutcome] = useState<Json | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [amend, setAmend] = useState<string>('')
  const [note, setNote] = useState('')

  const load = useCallback(() => {
    Promise.all([api.reviewQueue(), api.reviewStaff()])
      .then(([q, s]) => {
        setQueue(q)
        setStaff((s as { staff: Staff[] }).staff)
        const tasks = (q as Json).tasks as ReviewTask[]
        setSelected((prev) => prev ?? tasks[0]?.task_id ?? null)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(load, [load])

  useEffect(() => {
    if (!selected) {
      setDetail(null)
      return
    }
    setDetail(null)
    setOutcome(null)
    api
      .reviewTask(selected)
      .then((d) => {
        setDetail(d)
        setAmend(String(((d as Json).task as Json).proposed_amount_eur ?? ''))
        setNote('')
      })
      .catch((e: Error) => setError(e.message))
  }, [selected])

  const decide = async (decision: string) => {
    if (!selected) return
    setBusy(true)
    setError(null)
    try {
      const body: Json = { decision, user_id: actor, note }
      if (decision === 'amend') body.amount_eur = Number(amend)
      const res = await api.decideTask(selected, body)
      setOutcome(res)
      load()
      api.reviewTask(selected).then(setDetail).catch(() => undefined)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (error && !queue) return <ErrorNote message={error} />
  if (!queue) return <Spinner />

  const tasks = queue.tasks as ReviewTask[]
  const queues = queue.queues as Json[]
  const me = staff.find((s) => s.user_id === actor)

  return (
    <>
      <PageHeader
        eyebrow="Human authority"
        title="Review queues"
        lede="Where automation stops and a person decides. Approving does not bypass the control plane — it authorises a passage through it."
        right={
          <label className="flex items-center gap-2">
            <span className="text-[12px] text-ink-500">Acting as</span>
            <select
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              className="border border-ink-300 rounded px-2.5 py-1.5 text-[12.5px] bg-white focus:outline-none focus:border-az-500"
            >
              {staff.map((s) => (
                <option key={s.user_id} value={s.user_id}>
                  {s.name} — {s.role_label}
                </option>
              ))}
            </select>
          </label>
        }
      />

      {me && (
        <Card className="mb-5" dense>
          <div className="flex items-center gap-8">
            <div>
              <div className="text-[13px] font-medium text-ink-800">{me.name}</div>
              <div className="text-[11.5px] text-ink-500">{me.role_label} · {me.location}</div>
            </div>
            <div>
              <div className="text-[10.5px] uppercase tracking-[0.06em] text-ink-500">
                Settlement authority
              </div>
              <div className="text-[15px] font-semibold tabular text-ink-900">
                {me.authority_limit_eur > 0 ? eur(me.authority_limit_eur, 0) : 'None by design'}
              </div>
            </div>
            <div>
              <div className="text-[10.5px] uppercase tracking-[0.06em] text-ink-500">Queues</div>
              <div className="flex gap-1 mt-1">
                {me.queues.length ? (
                  me.queues.map((q) => (
                    <Badge key={q} tone="ghost">
                      {q}
                    </Badge>
                  ))
                ) : (
                  <span className="text-[12px] text-ink-500">read-only governance</span>
                )}
              </div>
            </div>
            <p className="text-[12px] text-ink-500 max-w-md ml-auto leading-snug">{me.note}</p>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-5 gap-4 mb-5">
        {queues.map((q) => (
          <Card key={q.queue as string} dense>
            <div className="flex items-baseline justify-between">
              <span className="text-[12px] font-medium text-ink-700">{q.queue as string}</span>
              <span className="text-[18px] font-semibold tabular text-ink-900">
                {num(q.open as number)}
              </span>
            </div>
            <div className="text-[11px] text-ink-500 mt-1 tabular">
              {eur(q.value_eur as number, 0)} at stake
            </div>
            {(q.sla_breached as number) > 0 && (
              <Badge tone="stop" className="mt-2">
                {String(q.sla_breached)} past SLA
              </Badge>
            )}
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-[340px_1fr] gap-5 items-start">
        <Card
          title="Prioritised work"
          subtitle="Value, SLA, risk, failed automation"
          dense
          pad={false}
        >
          {tasks.length === 0 ? (
            <div className="p-5">
              <Empty>Nothing waiting. Run a claim that trips the guard.</Empty>
            </div>
          ) : (
            <div className="py-1 max-h-[620px] overflow-y-auto">
              {tasks.map((t) => (
                <button
                  key={t.task_id}
                  type="button"
                  onClick={() => setSelected(t.task_id)}
                  className={`w-full text-left px-4 py-3 border-l-2 transition-colors ${
                    selected === t.task_id
                      ? 'border-az-700 bg-az-50'
                      : 'border-transparent hover:bg-ink-50'
                  }`}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge tone={t.queue === 'siu' ? 'stop' : 'warn'}>{t.queue}</Badge>
                    <Mono className="text-ink-700">{t.claim_reference}</Mono>
                    {t.sla_breached && <Badge tone="stop">SLA</Badge>}
                  </div>
                  <div className="text-[12px] text-ink-700 mt-1">
                    {t.reason.replace(/_/g, ' ')}
                  </div>
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="text-[11px] text-ink-500">
                      needs {t.authority_required}
                    </span>
                    <span className="text-[11.5px] font-medium tabular text-ink-800">
                      {t.proposed_amount_eur > 0 ? eur(t.proposed_amount_eur) : '—'}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>

        {!selected ? (
          <Empty>Select a task.</Empty>
        ) : !detail ? (
          <Spinner />
        ) : (
          <TaskDetail
            detail={detail}
            me={me}
            amend={amend}
            setAmend={setAmend}
            note={note}
            setNote={setNote}
            busy={busy}
            onDecide={decide}
            outcome={outcome}
            error={error}
            onOpenClaim={onOpenClaim}
          />
        )}
      </div>
    </>
  )
}

function TaskDetail({
  detail, me, amend, setAmend, note, setNote, busy, onDecide, outcome, error, onOpenClaim,
}: {
  detail: Json
  me?: Staff
  amend: string
  setAmend: (v: string) => void
  note: string
  setNote: (v: string) => void
  busy: boolean
  onDecide: (d: string) => void
  outcome: Json | null
  error: string | null
  onOpenClaim: (ref: string) => void
}) {
  const task = detail.task as Json
  const ws = detail.workspace as Json
  const claim = ws.claim as Json
  const coverage = ws.coverage as Json | null
  const estimates = ws.estimates as Json[]
  const risk = ws.risk as Json
  const docs = ws.documents as Json[]
  const pkg = ws.decision_package as Json | null

  const resolved = task.status === 'resolved'
  const proposed = Number(task.proposed_amount_eur ?? 0)
  const canApprove = (me?.authority_limit_eur ?? 0) >= proposed && (me?.authority_limit_eur ?? 0) > 0
  const inQueue = me ? me.queues.includes(task.queue as string) : false

  return (
    <div className="space-y-5">
      <Card
        title={`${task.claim_reference as string} · ${(task.reason as string).replace(/_/g, ' ')}`}
        subtitle={task.reason_detail as string}
        right={
          <div className="flex items-center gap-2">
            <Badge tone={resolved ? 'ok' : 'warn'}>{task.status as string}</Badge>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onOpenClaim(task.claim_reference as string)}
            >
              Open claim →
            </Button>
          </div>
        }
      >
        <KeyValueGrid cols={5}>
          <Field label="Policyholder">{claim?.policyholder?.name}</Field>
          <Field label="Cover">{claim?.policy?.product}</Field>
          <Field label="Agent proposed">
            <Badge tone={decisionTone(task.proposed_decision as string)}>
              {(task.proposed_decision as string) || '—'}
            </Badge>
          </Field>
          <Field label="Amount proposed">{eur(proposed)}</Field>
          <Field label="Authority required">
            <Badge tone={canApprove ? 'ok' : 'stop'}>{task.authority_required as string}</Badge>
          </Field>
        </KeyValueGrid>
      </Card>

      {/* Evidence workspace: document, extraction, clause and reasoning side by side */}
      <div className="grid grid-cols-3 gap-5">
        <Card title="Coverage" subtitle="With the clause relied on" dense>
          {!coverage ? (
            <Empty>No coverage view yet.</Empty>
          ) : (
            <>
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
              <p className="text-[12px] text-ink-600 mt-2.5 leading-snug">
                {coverage.reasoning as string}
              </p>
              <div className="mt-3 space-y-2">
                {(coverage.citations as Json[]).map((c) => (
                  <div key={c.clause_id as string} className="border-l-2 border-az-300 pl-2.5">
                    <Mono className="text-az-700 font-medium">{c.clause_id as string}</Mono>
                    <p className="text-[11px] text-ink-600 leading-snug mt-0.5 italic">
                      “{c.quote as string}”
                    </p>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>

        <Card title="Estimate" dense>
          {estimates.length === 0 ? (
            <Empty>No estimate yet.</Empty>
          ) : (
            (() => {
              const e = estimates[estimates.length - 1]
              return (
                <>
                  <div className="text-[20px] font-semibold tabular text-ink-900">
                    {eur(e.total_cost as number)}
                  </div>
                  <div className="text-[11.5px] text-ink-500 mt-1">
                    {eur(e.total_parts as number)} parts ·{' '}
                    {eur(e.total_labour as number)} labour ·{' '}
                    {eur(e.total_tax as number)} VAT
                  </div>
                  {e.reasonableness_band ? (
                    <Badge
                      tone={(e.reasonableness_band as string).includes('within') ? 'ok' : 'warn'}
                      className="mt-2"
                    >
                      {e.reasonableness_band as string}
                    </Badge>
                  ) : null}
                  <div className="mt-3 space-y-1">
                    {(e.items as Json[]).map((it, i) => (
                      <div key={i} className="flex justify-between text-[11.5px]">
                        <span className="text-ink-600">
                          {(it.part as string).replace(/_/g, ' ')} · {it.action as string}
                        </span>
                        <span className="tabular text-ink-800">
                          {eur(it.part_price_eur as number)}
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              )
            })()
          )}
        </Card>

        <Card title="Risk" dense>
          <div className="flex items-baseline gap-3">
            <span className="text-[20px] font-semibold tabular text-ink-900">
              {(risk.score as number).toFixed(2)}
            </span>
            <span className="text-[11.5px] text-ink-500">threshold 0.55</span>
          </div>
          <div className="mt-2">
            <Meter
              value={risk.score as number}
              tone={(risk.score as number) > 0.55 ? 'stop' : 'ok'}
            />
          </div>
          <div className="mt-3 space-y-2">
            {(risk.signals as Json[]).length === 0 ? (
              <p className="text-[12px] text-ink-500">No signals.</p>
            ) : (
              (risk.signals as Json[]).map((s, i) => (
                <div key={i}>
                  <div className="flex items-center gap-1.5">
                    <Badge tone="ghost" mono>
                      {(s.weight as number).toFixed(2)}
                    </Badge>
                    <span className="text-[11px] font-medium text-ink-700">
                      {(s.signal_type as string).replace(/_/g, ' ')}
                    </span>
                  </div>
                  <p className="text-[11px] text-ink-600 leading-snug mt-0.5">
                    {s.detail as string}
                  </p>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      {/* Decision controls */}
      <Card
        title="Decision"
        subtitle={
          resolved
            ? 'This task has been resolved.'
            : 'Approve, amend, reject or ask for more. Whatever you choose, the write is signed and verified.'
        }
      >
        {resolved ? (
          <div className="flex items-center gap-3 flex-wrap">
            <Badge tone={decisionTone(task.decision as string)}>{task.decision as string}</Badge>
            <span className="text-[12.5px] text-ink-600">
              by {task.resolved_by as string} · {when(task.resolved_at as string)}
            </span>
            {task.approval_ref ? <Mono>{task.approval_ref as string}</Mono> : null}
            {task.decision_note ? (
              <p className="text-[12.5px] text-ink-600 w-full mt-1">
                “{task.decision_note as string}”
              </p>
            ) : null}
          </div>
        ) : (
          <>
            {!inQueue && (
              <div className="mb-4 border border-warn-100 bg-warn-100 rounded px-3.5 py-2.5 text-[12.5px] text-warn-700">
                {me?.name} does not work the {task.queue as string} queue. Switch the acting
                user to someone who does.
              </div>
            )}
            {!canApprove && proposed > 0 && (
              <div className="mb-4 border border-stop-100 bg-stop-100 rounded px-3.5 py-2.5 text-[12.5px] text-stop-700">
                {eur(proposed)} is above {me?.name}’s authority of{' '}
                {eur(me?.authority_limit_eur ?? 0, 0)}. Approving will be refused before
                anything is signed — that is the check, not the button being hidden.
              </div>
            )}
            <div className="flex items-end gap-4 flex-wrap">
              <label className="block">
                <span className="text-[11px] font-medium uppercase tracking-[0.055em] text-ink-500">
                  Amount to settle
                </span>
                <div className="flex items-center gap-1.5 mt-1">
                  <span className="text-[12.5px] text-ink-500">EUR</span>
                  <input
                    value={amend}
                    onChange={(e) => setAmend(e.target.value)}
                    className="w-32 border border-ink-300 rounded px-2 py-1.5 text-[13px] font-mono tabular focus:outline-none focus:border-az-500"
                  />
                </div>
              </label>
              <label className="flex-1 min-w-[280px] block">
                <span className="text-[11px] font-medium uppercase tracking-[0.055em] text-ink-500">
                  Note for the record
                </span>
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Why this decision"
                  className="mt-1 w-full border border-ink-300 rounded px-2.5 py-1.5 text-[12.5px] focus:outline-none focus:border-az-500"
                />
              </label>
            </div>
            <div className="flex gap-2 mt-4">
              <Button onClick={() => onDecide('approve')} busy={busy}>
                Approve {eur(proposed)}
              </Button>
              <Button variant="secondary" onClick={() => onDecide('amend')} busy={busy}>
                Approve amended {eur(Number(amend) || 0)}
              </Button>
              <Button variant="secondary" onClick={() => onDecide('request_more')} busy={busy}>
                Request more
              </Button>
              <Button variant="danger" onClick={() => onDecide('reject')} busy={busy}>
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

      {outcome && <DecisionOutcome outcome={outcome} />}

      {pkg && (
        <Card title="Last signed action on this claim" dense>
          <KeyValueGrid cols={4}>
            <Field label="Action" mono>{pkg.action as string}</Field>
            <Field label="Nonce" mono>{String(pkg.nonce)}</Field>
            <Field label="Agent" mono>{pkg.agent_id as string}</Field>
            <Field label="Status">
              <Badge tone={pkg.verification_status === 'VERIFIED_AUTHENTIC' ? 'ok' : 'stop'}>
                {pkg.verification_status as string}
              </Badge>
            </Field>
          </KeyValueGrid>
        </Card>
      )}

      {docs.length > 0 && (
        <Card title="Evidence" subtitle="Document, extraction and reasoning side by side" dense>
          <Table head={['Document', 'Type', 'Quality', 'Fields', 'Lowest confidence']}>
            {docs.map((d) => {
              const fields = (d.fields as Json[]) ?? []
              const lowest = fields.length
                ? Math.min(...fields.map((f) => f.confidence as number))
                : null
              return (
                <tr key={d.doc_id as string}>
                  <Td mono>{d.filename as string}</Td>
                  <Td>{d.doc_type as string}</Td>
                  <Td align="right">
                    <Badge
                      tone={
                        (d.quality_score as number) >= 0.85
                          ? 'ok'
                          : (d.quality_score as number) >= 0.55
                            ? 'warn'
                            : 'stop'
                      }
                    >
                      {(d.quality_score as number).toFixed(2)}
                    </Badge>
                  </Td>
                  <Td align="right">{fields.length}</Td>
                  <Td align="right">
                    {lowest !== null ? (
                      <span className={lowest < 0.85 ? 'text-warn-700' : ''}>
                        {lowest.toFixed(2)}
                      </span>
                    ) : (
                      '—'
                    )}
                  </Td>
                </tr>
              )
            })}
          </Table>
        </Card>
      )}
    </div>
  )
}

function DecisionOutcome({ outcome }: { outcome: Json }) {
  const accepted = outcome.accepted as boolean
  if (!accepted) {
    return (
      <Card title="Refused" dense>
        <div className="border border-stop-100 bg-stop-100 rounded px-3.5 py-2.5">
          <div className="text-[12.5px] font-medium text-stop-700 mb-1">
            {(outcome.reason as string).replace(/_/g, ' ')}
          </div>
          <p className="text-[12px] text-stop-700">
            {eur(outcome.required_authority_eur as number)} requires more than the{' '}
            {eur(outcome.your_authority_eur as number, 0)} authority held. Nothing was
            signed and nothing was written.
          </p>
        </div>
        <ul className="mt-3">
          {(outcome.steps as Json[]).map((s, i) => (
            <CheckRow
              key={i}
              passed={s.passed as boolean}
              label={(s.step as string).replace(/_/g, ' ')}
              detail={s.detail as string}
            />
          ))}
        </ul>
      </Card>
    )
  }

  const approver = outcome.approver as Json
  const audit = outcome.audit as Json

  return (
    <Card
      title="Written once, signed"
      subtitle="A human decision travels the same path as an autonomous one"
      dense
      right={<Badge tone="ok">{outcome.recorded_decision as string}</Badge>}
    >
      <KeyValueGrid cols={4}>
        <Field label="Approver">
          {approver.name as string}
          <div className="text-[11px] text-ink-500">{approver.role as string}</div>
        </Field>
        <Field label="Settled">{eur(outcome.settlement_amount_eur as number)}</Field>
        <Field label="Approval" mono>{(outcome.approval_ref as string) ?? '—'}</Field>
        <Field label="Row audit">
          <Badge tone={audit.healthy ? 'ok' : 'stop'}>
            {audit.healthy ? 'clean' : `${String(audit.tampered_count)} flagged`}
          </Badge>
        </Field>
      </KeyValueGrid>
      <ul className="mt-4">
        {(outcome.steps as Json[]).map((s, i) => (
          <CheckRow
            key={i}
            passed={s.passed as boolean}
            label={(s.step as string).replace(/_/g, ' ')}
            detail={s.detail as string}
          />
        ))}
      </ul>
      {outcome.write ? (
        <details className="mt-3">
          <summary className="text-[11.5px] text-az-700 cursor-pointer hover:underline">
            Gateway checks in full
          </summary>
          <div className="mt-2">
            <JsonBlock value={outcome.write} maxHeight={240} />
          </div>
        </details>
      ) : null}
    </Card>
  )
}
