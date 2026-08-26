import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import {
  Avatar, Button, Card, Chip, Empty, ErrorNote, Meter, PageHeader, Spinner, Stat,
  Table, Td,
} from '../components/ui'
import { eur, num, pct } from '../lib/format'
import type { Json, Persona } from '../types'

export function TeamView({ persona, refreshKey }: { persona: Persona; refreshKey: number }) {
  const [metrics, setMetrics] = useState<Json | null>(null)
  const [queue, setQueue] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    Promise.all([api.metrics(), api.reviewQueue()])
      .then(([m, q]) => {
        setMetrics(m)
        setQueue(q)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    setMetrics(null)
    load()
  }, [load, refreshKey])

  if (error) return <ErrorNote message={error} />
  if (!metrics || !queue) return <Spinner />

  const headline = (metrics.headline as Json[]) ?? []
  const queues = (queue.queues as Json[]) ?? []
  const tasks = (queue.tasks as Json[]) ?? []

  const byReason: Record<string, number> = {}
  for (const t of tasks) {
    const key = String(t.reason ?? 'unknown')
    byReason[key] = (byReason[key] ?? 0) + 1
  }
  const reasons = Object.entries(byReason).sort((a, b) => b[1] - a[1])
  const maxReason = Math.max(1, ...reasons.map(([, n]) => n))

  return (
    <>
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-2">
            <Avatar initials={persona.initials} accent={persona.accent} size={20} />
            {persona.role_label}
          </span>
        }
        title="Team"
        lede="Throughput, SLA pressure, and where automation is stopping most often. Where it stops is yours to fix, not the platform's to hide."
        right={
          <Button variant="secondary" size="sm" onClick={load}>
            Refresh
          </Button>
        }
      />

      <Card
        title="The five measures"
        subtitle="Each computed from claim rows rather than asserted"
        className="mb-5"
      >
        <div className="grid grid-cols-5 gap-8">
          {headline.map((h) => {
            const measured = Number(h.denominator ?? 0) > 0 || h.format === 'hours'
            const v = h.value as number
            return (
              <div key={h.key as string}>
                <Stat
                  label={h.label as string}
                  value={
                    h.format === 'percent'
                      ? measured
                        ? pct(v, 0)
                        : '—'
                      : `${num(v, 1)} h`
                  }
                  tone={
                    h.format !== 'percent'
                      ? 'blue'
                      : !measured
                        ? 'ghost'
                        : v >= 0.8
                          ? 'ok'
                          : v >= 0.5
                            ? 'warn'
                            : 'stop'
                  }
                  sub={h.sublabel as string}
                />
                {h.format === 'percent' && measured && (
                  <div className="mt-3">
                    <Meter
                      value={v}
                      tone={v >= 0.8 ? 'ok' : v >= 0.5 ? 'warn' : 'stop'}
                    />
                    <div className="text-[11px] text-ink-400 mt-1.5 tabular">
                      {num(h.numerator as number)} of {num(h.denominator as number)}
                    </div>
                  </div>
                )}
                {h.format === 'percent' && !measured && (
                  <div className="mt-3 text-[11px] text-ink-400">
                    Nothing measured yet.
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        <Card title="Open work by queue" subtitle="And what is at stake on each">
          {queues.length === 0 ? (
            <Empty>Every queue is clear.</Empty>
          ) : (
            <Table head={['Queue', 'Open', 'Resolved', 'Past SLA', 'At stake']}>
              {queues.map((q) => (
                <tr key={q.queue as string}>
                  <Td>{String(q.queue).replace(/_/g, ' ')}</Td>
                  <Td align="right">{num(q.open as number)}</Td>
                  <Td align="right">{num(q.resolved as number)}</Td>
                  <Td align="right">
                    {(q.sla_breached as number) > 0 ? (
                      <Chip tone="stop">{String(q.sla_breached)}</Chip>
                    ) : (
                      '—'
                    )}
                  </Td>
                  <Td align="right">{eur(q.value_eur as number, 0)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card
          title="Where automation stopped"
          subtitle="By reason, not as one number — an override rate you cannot decompose tells you nothing"
        >
          {reasons.length === 0 ? (
            <Empty>Nothing stopped. Every claim finished on its own.</Empty>
          ) : (
            <div className="space-y-3">
              {reasons.map(([reason, count]) => (
                <div key={reason} className="flex items-center gap-3">
                  <span className="w-[180px] shrink-0 text-[12.5px] text-ink-700">
                    {reason.replace(/_/g, ' ')}
                  </span>
                  <div className="flex-1">
                    <Meter value={count / maxReason} tone="warn" />
                  </div>
                  <span className="w-8 text-right text-[13px] tabular text-ink-900">
                    {count}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
