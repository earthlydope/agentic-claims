import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import {
  Badge, Button, Card, decisionTone, Empty, ErrorNote, PageHeader, Spinner,
  statusTone, Table, Tabs, Td,
} from '../components/ui'
import { ago, eur, num, PRODUCT_LABEL } from '../lib/format'
import type { Claim } from '../types'

type Filter = 'live' | 'review' | 'approved' | 'all'

export function Claims({
  onOpen, refreshKey,
}: { onOpen: (ref: string) => void; refreshKey: number }) {
  const [claims, setClaims] = useState<Claim[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('live')

  useEffect(() => {
    setClaims(null)
    api
      .claims(false)
      .then((d) => setClaims((d as { claims: Claim[] }).claims))
      .catch((e: Error) => setError(e.message))
  }, [refreshKey])

  const counts = useMemo(() => {
    const all = claims ?? []
    return {
      live: all.filter((c) => c.is_live_demo).length,
      review: all.filter((c) => c.status === 'in_review').length,
      approved: all.filter((c) => c.decision === 'Approved').length,
      all: all.length,
    }
  }, [claims])

  const shown = useMemo(() => {
    const all = claims ?? []
    if (filter === 'live') return all.filter((c) => c.is_live_demo)
    if (filter === 'review') return all.filter((c) => c.status === 'in_review')
    if (filter === 'approved') return all.filter((c) => c.decision === 'Approved')
    return all
  }, [claims, filter])

  if (error) return <ErrorNote message={error} />

  return (
    <>
      <PageHeader
        eyebrow="Claims"
        title="Claim list"
        lede="The five demo claims are the ones with a scenario attached. The rest are a twelve-week historical portfolio so the measures are read from real rows."
      />
      <Card pad={false}>
        <div className="px-5 pt-4">
          <Tabs
            tabs={[
              { id: 'live' as Filter, label: 'Demo claims', count: counts.live },
              { id: 'review' as Filter, label: 'In review', count: counts.review },
              { id: 'approved' as Filter, label: 'Approved', count: counts.approved },
              { id: 'all' as Filter, label: 'All', count: counts.all },
            ]}
            active={filter}
            onChange={setFilter}
          />
        </div>
        <div className="p-5">
          {!claims ? (
            <Spinner />
          ) : shown.length === 0 ? (
            <Empty>Nothing in this view.</Empty>
          ) : (
            <Table
              head={[
                'Claim', 'Policyholder', 'Cover', 'Incident', 'Severity', 'Status',
                'Outcome', 'Settled', '',
              ]}
            >
              {shown.map((c) => (
                <tr key={c.reference} className="hover:bg-ink-50/60 group">
                  <Td mono>
                    <button
                      type="button"
                      onClick={() => onOpen(c.reference)}
                      className="text-az-700 hover:underline font-medium"
                    >
                      {c.reference}
                    </button>
                    <div className="text-[10.5px] text-ink-400 font-sans mt-0.5">
                      {ago(c.reported_at)}
                    </div>
                  </Td>
                  <Td>
                    <div className="text-ink-800">{c.policyholder?.name ?? '—'}</div>
                    <div className="text-[11px] text-ink-500">{c.incident_region}</div>
                  </Td>
                  <Td>
                    <div className="text-ink-700">{c.policy?.product ?? '—'}</div>
                    <div className="text-[11px] text-ink-500">
                      {PRODUCT_LABEL[c.policy?.product ?? ''] ?? ''}
                    </div>
                  </Td>
                  <Td>
                    <div className="text-ink-700">
                      {(c.incident_type ?? '—').replace(/_/g, ' ')}
                    </div>
                    {c.injury_reported && (
                      <Badge tone="stop" className="mt-1">
                        injury
                      </Badge>
                    )}
                  </Td>
                  <Td>
                    {c.severity ? (
                      <Badge tone={c.severity === 'complex' ? 'warn' : 'neutral'}>
                        {c.severity}
                      </Badge>
                    ) : (
                      <span className="text-ink-400">—</span>
                    )}
                    {c.structural_damage && (
                      <div className="text-[10.5px] text-warn-700 mt-1">structural</div>
                    )}
                  </Td>
                  <Td>
                    <Badge tone={statusTone(c.status)}>{c.status.replace(/_/g, ' ')}</Badge>
                    {c.assigned_queue && (
                      <div className="text-[10.5px] text-ink-500 mt-1">{c.assigned_queue}</div>
                    )}
                  </Td>
                  <Td>
                    {c.decision ? (
                      <Badge tone={decisionTone(c.decision)}>{c.decision}</Badge>
                    ) : (
                      <span className="text-ink-400">—</span>
                    )}
                    {c.straight_through && (
                      <div className="text-[10.5px] text-ok-700 mt-1">straight through</div>
                    )}
                  </Td>
                  <Td align="right">
                    {c.settlement_amount_eur > 0 ? eur(c.settlement_amount_eur) : '—'}
                  </Td>
                  <Td align="right">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => onOpen(c.reference)}
                      className="opacity-0 group-hover:opacity-100"
                    >
                      Open →
                    </Button>
                  </Td>
                </tr>
              ))}
            </Table>
          )}
          {claims && (
            <div className="mt-4 text-[11.5px] text-ink-500">
              {num(shown.length)} of {num(claims.length)} claims
            </div>
          )}
        </div>
      </Card>
    </>
  )
}
