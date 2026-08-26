import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import {
  Badge, Button, Card, decisionTone, Empty, ErrorNote, Field, JsonBlock,
  KeyValueGrid, Meter, Mono, PageHeader, Spinner, Stat, Table, Tabs, Td,
} from '../components/ui'
import { eur, ms, num, pct, when } from '../lib/format'
import type { Json } from '../types'

type Tab = 'runs' | 'topology' | 'evals'

export function Observability() {
  const [tab, setTab] = useState<Tab>('runs')
  const [data, setData] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.observability(40).then(setData).catch((e: Error) => setError(e.message))
  }, [])

  useEffect(load, [load])

  if (error) return <ErrorNote message={error} />
  if (!data) return <Spinner />

  const totals = data.totals as Json
  const harness = data.harness as Json

  return (
    <>
      <PageHeader
        eyebrow="Observability, evaluation & FinOps"
        title="One trace from the customer tap to the signed write"
        lede="And continuous proof that quality has not drifted. Every figure here is read back from the runs that actually happened."
        right={
          <Button variant="secondary" onClick={load}>
            Refresh
          </Button>
        }
      />

      <div className="grid grid-cols-6 gap-4 mb-5">
        <Card dense>
          <Stat label="Runs" value={num(totals.run_count as number)} sub={`${String(totals.completed)} completed`} />
        </Card>
        <Card dense>
          <Stat label="Avg duration" value={ms(totals.avg_duration_ms as number)} />
        </Card>
        <Card dense>
          <Stat label="Avg tool calls" value={num(totals.avg_tool_calls as number, 1)} />
        </Card>
        <Card dense>
          <Stat label="Tokens" value={num(totals.total_tokens as number)} sub={`${num(totals.avg_tokens_per_run as number)} per run`} />
        </Card>
        <Card dense>
          <Stat label="Cost per claim" value={eur(totals.cost_per_claim_eur as number, 4)} tone="blue" />
        </Card>
        <Card dense>
          <Stat
            label="Model"
            value={harness.model_mode === 'live-gemini' ? 'Gemini' : 'Deterministic'}
            tone={harness.model_mode === 'live-gemini' ? 'ok' : 'blue'}
            mono={false}
            sub={harness.model_fast as string}
          />
        </Card>
      </div>

      <div className="border-b border-ink-200 mb-5">
        <Tabs
          tabs={[
            { id: 'runs' as Tab, label: 'Runs & traces', count: (data.runs as Json[]).length },
            { id: 'topology' as Tab, label: 'Agent topology' },
            { id: 'evals' as Tab, label: 'Evaluations' },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      {tab === 'runs' && <Runs data={data} />}
      {tab === 'topology' && <Topology data={data} />}
      {tab === 'evals' && <Evals />}
    </>
  )
}

function Runs({ data }: { data: Json }) {
  const runs = data.runs as Json[]
  const [open, setOpen] = useState<string | null>(null)
  const [detail, setDetail] = useState<Json | null>(null)

  useEffect(() => {
    if (!open) {
      setDetail(null)
      return
    }
    api.run(open).then(setDetail).catch(() => undefined)
  }, [open])

  return (
    <div className="space-y-5">
      <Card
        title="Recent runs"
        subtitle="Every run is one trace: user → workflow → agent → tool → signed write"
        pad={false}
      >
        <div className="p-5">
          {runs.length === 0 ? (
            <Empty>No runs yet. Run a claim.</Empty>
          ) : (
            <Table
              head={['Run', 'Claim', 'Outcome', 'Steps', 'Tools', 'Tokens', 'Cost', 'Duration', 'Trigger', 'When']}
            >
              {runs.map((r) => (
                <tr
                  key={r.run_id as string}
                  className={`hover:bg-ink-50/60 cursor-pointer ${
                    open === r.run_id ? 'bg-az-50' : ''
                  }`}
                  onClick={() => setOpen(open === r.run_id ? null : (r.run_id as string))}
                >
                  <Td mono>{r.run_id as string}</Td>
                  <Td mono>{r.claim_reference as string}</Td>
                  <Td>
                    <Badge tone={decisionTone(r.outcome as string)}>
                      {(r.outcome as string) ?? (r.status as string)}
                    </Badge>
                    {(r.budget_stops as string[])?.length > 0 && (
                      <Badge tone="warn" className="ml-1">
                        safe stop
                      </Badge>
                    )}
                  </Td>
                  <Td align="right">{String(r.steps_completed)}</Td>
                  <Td align="right">{String(r.tool_calls)}</Td>
                  <Td align="right">{num(r.total_tokens as number)}</Td>
                  <Td align="right">{eur(r.cost_eur as number, 4)}</Td>
                  <Td align="right">{ms(r.duration_ms as number)}</Td>
                  <Td>{r.trigger as string}</Td>
                  <Td>{when(r.started_at as string)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      </Card>

      {open && (
        <Card
          title={`Trace · ${open}`}
          subtitle={detail ? `${(detail.trace as Json[]).length} events` : 'Loading…'}
          pad={false}
        >
          {!detail ? (
            <Spinner />
          ) : (
            <div className="p-5">
              <KeyValueGrid cols={6}>
                <Field label="Status">{detail.status as string}</Field>
                <Field label="Outcome">{(detail.outcome as string) ?? '—'}</Field>
                <Field label="Prompt tokens">{num(detail.prompt_tokens as number)}</Field>
                <Field label="Completion tokens">{num(detail.completion_tokens as number)}</Field>
                <Field label="Cost">{eur(detail.cost_eur as number, 4)}</Field>
                <Field label="Model mode" mono>{detail.model_mode as string}</Field>
              </KeyValueGrid>
              <div className="mt-5 max-h-[420px] overflow-y-auto border border-ink-200 rounded">
                <Table head={['', 'Step', 'Kind', 'Agent', 'Detail', 'Elapsed']}>
                  {(detail.trace as Json[]).map((e) => (
                    <tr key={e.seq as number}>
                      <Td mono>{String(e.seq)}</Td>
                      <Td mono>{(e.step_id as string) ?? '—'}</Td>
                      <Td>{(e.kind as string).replace(/_/g, ' ')}</Td>
                      <Td>{(e.agent as string) ?? '—'}</Td>
                      <Td className="max-w-[520px]">
                        <span className="text-ink-600">{e.detail as string}</span>
                      </Td>
                      <Td align="right">{ms(e.elapsed_ms as number)}</Td>
                    </tr>
                  ))}
                </Table>
              </div>
            </div>
          )}
        </Card>
      )}

      <div className="grid grid-cols-2 gap-5">
        <Card
          title="Tool ledger"
          subtitle="Which capabilities were actually exercised, and how often"
          dense
        >
          {Object.keys(data.tool_ledger as Json).length === 0 ? (
            <Empty>No tool calls recorded.</Empty>
          ) : (
            <div className="space-y-1.5">
              {Object.entries(data.tool_ledger as Record<string, number>).map(([tool, count]) => {
                const max = Math.max(...Object.values(data.tool_ledger as Record<string, number>))
                return (
                  <div key={tool} className="flex items-center gap-2.5">
                    <Mono className="w-[192px] shrink-0 truncate">{tool}</Mono>
                    <div className="flex-1">
                      <Meter value={count / max} height={4} />
                    </div>
                    <span className="text-[11.5px] text-ink-500 tabular w-7 text-right">
                      {count}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        <Card title="Step latency" subtitle="Mean elapsed time at each step boundary" dense>
          {Object.keys(data.step_latency_ms as Json).length === 0 ? (
            <Empty>No steps recorded.</Empty>
          ) : (
            <div className="space-y-1.5">
              {Object.entries(data.step_latency_ms as Record<string, number>).map(([step, v]) => {
                const max = Math.max(
                  ...Object.values(data.step_latency_ms as Record<string, number>),
                )
                return (
                  <div key={step} className="flex items-center gap-2.5">
                    <Mono className="w-[168px] shrink-0 truncate">{step}</Mono>
                    <div className="flex-1">
                      <Meter value={v / max} height={4} tone="blue" />
                    </div>
                    <span className="text-[11.5px] text-ink-500 tabular w-[62px] text-right">
                      {ms(v)}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

function Topology({ data }: { data: Json }) {
  const topology = data.topology as Json
  const agents = topology.agents as Json[]
  const max = Math.max(1, ...agents.map((a) => a.calls as number))

  return (
    <div className="space-y-5">
      <Card title="Composition" dense>
        <div className="font-mono text-[11.5px] text-ink-700 bg-ink-50 border border-ink-200 rounded p-3.5 leading-relaxed overflow-x-auto">
          {topology.composition as string}
        </div>
      </Card>
      <Card title="Agent activity" subtitle="Events authored by each agent across recent runs">
        <div className="space-y-3">
          {agents.map((a) => (
            <div key={a.key as string} className="flex items-center gap-3">
              <span className="w-6 h-6 shrink-0 rounded bg-az-700 text-white text-[11px] font-semibold grid place-items-center">
                {a.ordinal as number}
              </span>
              <div className="w-[188px] shrink-0">
                <div className="text-[12.5px] font-medium text-ink-800">{a.title as string}</div>
                <Mono className="text-ink-400">{a.model_tier as string}</Mono>
              </div>
              <div className="flex-1">
                <Meter value={(a.calls as number) / max} height={6} />
              </div>
              <span className="text-[12px] text-ink-600 tabular w-10 text-right">
                {num(a.calls as number)}
              </span>
              <div className="w-[280px] shrink-0 flex flex-wrap gap-1">
                {(a.tool_scope as string[]).map((t) => (
                  <Badge key={t} tone="ghost" mono>
                    {t}
                  </Badge>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

function Evals() {
  const [cases, setCases] = useState<Json | null>(null)
  const [result, setResult] = useState<Json | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.evalCases().then(setCases).catch(() => undefined)
  }, [])

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      setResult(await api.runEvals())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <Card
        title="Golden cases"
        subtitle="Each case asserts the outcome, the routing, the exact set of policy checks that should fail, groundedness, the amount written, and the tool trajectory. Nothing is mocked — the platform actually runs."
        right={
          <div className="flex items-center gap-2">
            {result && (
              <Badge tone={result.failed === 0 ? 'ok' : 'stop'}>
                {String(result.passed)}/{String(result.cases)} cases ·{' '}
                {String((result.assertions as Json).passed)}/
                {String((result.assertions as Json).total)} assertions
              </Badge>
            )}
            <Button onClick={run} busy={busy}>
              Run the suite
            </Button>
          </div>
        }
      >
        {error && <ErrorNote message={error} />}
        {busy && <Spinner label="Replaying every golden case against the live platform…" />}
        {!result && !busy && cases ? (
          <Table head={['Claim', 'Case', 'Expected outcome', 'Expected queue', 'Expected checks']}>
            {(cases.cases as Json[]).map((c) => (
              <tr key={c.reference as string}>
                <Td mono>{c.reference as string}</Td>
                <Td>{c.name as string}</Td>
                <Td>
                  <Badge tone={decisionTone(c.expect_decision as string)}>
                    {c.expect_decision as string}
                  </Badge>
                </Td>
                <Td>{(c.expect_queue as string) ?? 'none'}</Td>
                <Td mono>{((c.expect_failed_checks as string[]) ?? []).join(', ') || '—'}</Td>
              </tr>
            ))}
          </Table>
        ) : null}

        {result && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-5">
              <Stat
                label="Cases"
                value={`${String(result.passed)}/${String(result.cases)}`}
                tone={result.failed === 0 ? 'ok' : 'stop'}
              />
              <Stat
                label="Assertions"
                value={pct((result.assertions as Json).pass_rate as number, 0)}
                tone={
                  ((result.assertions as Json).pass_rate as number) === 1 ? 'ok' : 'stop'
                }
                sub={`${String((result.assertions as Json).passed)} of ${String(
                  (result.assertions as Json).total,
                )}`}
              />
              <Stat
                label="Dimensions"
                value={num((result.dimensions as string[]).length)}
                sub={(result.dimensions as string[]).join(' · ')}
              />
            </div>
            {(result.results as Json[]).map((r) => (
              <div key={r.reference as string} className="border border-ink-200 rounded">
                <div className="flex items-center gap-2.5 px-4 py-2.5 border-b border-ink-100">
                  <Badge tone={r.passed ? 'ok' : 'stop'}>{r.passed ? 'pass' : 'FAIL'}</Badge>
                  <Mono className="text-ink-700">{r.reference as string}</Mono>
                  <span className="text-[12.5px] text-ink-700">{r.name as string}</span>
                  <span className="ml-auto text-[11.5px] text-ink-500">
                    {(r.observed as Json).tools_called
                      ? `${((r.observed as Json).tools_called as string[]).length} tools`
                      : ''}
                  </span>
                </div>
                <div className="px-4 py-3">
                  <Table head={['Assertion', 'Expected', 'Actual', '']}>
                    {(r.assertions as Json[]).map((a) => (
                      <tr key={a.assertion as string}>
                        <Td>{(a.assertion as string).replace(/_/g, ' ')}</Td>
                        <Td mono>{JSON.stringify(a.expected)}</Td>
                        <Td mono>{JSON.stringify(a.actual)}</Td>
                        <Td>
                          <Badge tone={a.passed ? 'ok' : 'stop'}>{a.passed ? '✓' : '✗'}</Badge>
                        </Td>
                      </tr>
                    ))}
                  </Table>
                  <details className="mt-3">
                    <summary className="text-[11.5px] text-az-700 cursor-pointer hover:underline">
                      Observed run
                    </summary>
                    <div className="mt-2">
                      <JsonBlock value={r.observed} maxHeight={260} />
                    </div>
                  </details>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
