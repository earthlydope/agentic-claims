import { useEffect, useState } from 'react'
import { api } from '../api'
import {
  Badge, Button, Card, decisionTone, Dot, Empty, ErrorNote, Meter, PageHeader,
  Spinner, Stat, statusTone, Table, Td,
} from '../components/ui'
import { ago, eur, num, pct, PRODUCT_LABEL } from '../lib/format'
import type { Claim, Json } from '../types'

/** A rate with no denominator has not been measured — it is not zero. */
function measured(h: Json): boolean {
  return Number(h.denominator ?? 0) > 0
}

export function Overview({
  onNavigate, onOpenClaim, refreshKey,
}: { onNavigate: (r: string) => void; onOpenClaim: (ref: string) => void; refreshKey: number }) {
  const [metrics, setMetrics] = useState<Json | null>(null)
  const [claims, setClaims] = useState<Claim[]>([])
  const [posture, setPosture] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setMetrics(null)
    Promise.all([api.metrics(), api.claims(true), api.posture()])
      .then(([m, c, p]) => {
        setMetrics(m)
        setClaims((c as { claims: Claim[] }).claims)
        setPosture(p)
      })
      .catch((e: Error) => setError(e.message))
  }, [refreshKey])

  if (error) return <ErrorNote message={error} />
  if (!metrics || !posture) return <Spinner />

  const headline = metrics.headline as Json[]
  const portfolio = metrics.portfolio as Json
  const ledger = posture.ledger as Json
  const audit = ledger.database_audit as Json

  return (
    <>
      <PageHeader
        eyebrow="Agentic motor claims"
        title="Claims operations"
        lede="Nine Google ADK agents grounded on a governed semantic layer, wrapped in three zero-trust pillars. Agents recommend, deterministic services decide, people approve."
        right={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => onNavigate('file')}>
              File a claim
            </Button>
            <Button onClick={() => onNavigate('claims')}>Open the claim list</Button>
          </div>
        }
      />

      {/* The five measures a claims leader reads on a Monday morning */}
      <Card
        title="The five measures"
        subtitle="Every one computed from claim rows, not asserted"
        className="mb-5"
      >
        <div className="grid grid-cols-5 gap-6 divide-x divide-ink-100">
          {headline.map((h, i) => (
            <div key={h.key as string} className={i > 0 ? 'pl-6' : ''}>
              <Stat
                label={h.label as string}
                value={
                  h.format === 'percent'
                    ? measured(h)
                      ? pct(h.value as number, 0)
                      : '—'
                    : `${num(h.value as number, 1)} h`
                }
                tone={
                  h.format !== 'percent'
                    ? 'blue'
                    : !measured(h)
                      ? 'ghost'
                      : (h.value as number) >= 0.8
                        ? 'ok'
                        : (h.value as number) >= 0.5
                          ? 'warn'
                          : 'stop'
                }
                sub={h.sublabel as string}
              />
              {h.format === 'percent' && !measured(h) && (
                <div className="mt-3 text-[10.5px] text-ink-400">
                  Nothing measured yet — run a claim.
                </div>
              )}
              {h.format === 'percent' && measured(h) && (
                <div className="mt-3">
                  <Meter
                    value={h.value as number}
                    tone={
                      (h.value as number) >= 0.8 ? 'ok' : (h.value as number) >= 0.5 ? 'warn' : 'stop'
                    }
                  />
                  <div className="text-[10.5px] text-ink-400 mt-1.5 tabular">
                    {num(h.numerator as number)} of {num(h.denominator as number)}
                  </div>
                </div>
              )}
              {h.format === 'hours' && h.breakdown && (
                <div className="mt-3 space-y-1">
                  {Object.entries(h.breakdown as Record<string, number>)
                    .slice(0, 3)
                    .map(([k, v]) => (
                      <div key={k} className="flex justify-between text-[10.5px] text-ink-500">
                        <span className="truncate pr-2">{k.replace(/_/g, ' ')}</span>
                        <span className="tabular">{num(v, 1)} h</span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-[1fr_320px] gap-5">
        {/* Live demo claims */}
        <Card
          title="The five demo claims"
          subtitle="Each one exercises a different path through the platform"
          right={
            <Badge tone="ghost">{claims.length} live</Badge>
          }
          pad={false}
        >
          <div className="px-5 pb-4 pt-4">
            {claims.length === 0 ? (
              <Empty>No live claims. Reset the demo data to restore them.</Empty>
            ) : (
              <Table head={['Claim', 'Policyholder', 'Cover', 'Scenario', 'Status', 'Outcome', '']}>
                {claims.map((c) => (
                  <tr key={c.reference} className="hover:bg-ink-50/60 group">
                    <Td mono>
                      <button
                        type="button"
                        onClick={() => onOpenClaim(c.reference)}
                        className="text-az-700 hover:underline font-medium"
                      >
                        {c.reference}
                      </button>
                      <div className="text-[10.5px] text-ink-400 font-sans mt-0.5">
                        {ago(c.reported_at)}
                      </div>
                    </Td>
                    <Td>
                      <div className="font-medium text-ink-800">{c.policyholder?.name}</div>
                      <div className="text-[11px] text-ink-500">
                        {c.policyholder?.city} · {c.language.toUpperCase()}
                      </div>
                    </Td>
                    <Td>
                      <div className="text-ink-700">{c.policy?.product}</div>
                      <div className="text-[11px] text-ink-500">
                        {PRODUCT_LABEL[c.policy?.product ?? ''] ?? ''}
                      </div>
                    </Td>
                    <Td>
                      <div className="text-ink-700">{c.scenario?.title}</div>
                      <div className="text-[11px] text-ink-500 leading-snug max-w-[260px]">
                        {c.scenario?.headline}
                      </div>
                    </Td>
                    <Td>
                      <Badge tone={statusTone(c.status)}>{c.status.replace(/_/g, ' ')}</Badge>
                      {c.open_task && (
                        <div className="text-[10.5px] text-ink-500 mt-1">
                          → {c.open_task.queue}
                        </div>
                      )}
                    </Td>
                    <Td align="right">
                      {c.decision ? (
                        <>
                          <Badge tone={decisionTone(c.decision)}>{c.decision}</Badge>
                          {c.settlement_amount_eur > 0 && (
                            <div className="text-[11.5px] text-ink-700 mt-1 tabular">
                              {eur(c.settlement_amount_eur)}
                            </div>
                          )}
                        </>
                      ) : (
                        <span className="text-ink-400">not run</span>
                      )}
                    </Td>
                    <Td align="right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onOpenClaim(c.reference)}
                        className="opacity-0 group-hover:opacity-100"
                      >
                        Open →
                      </Button>
                    </Td>
                  </tr>
                ))}
              </Table>
            )}
          </div>
        </Card>

        <div className="space-y-5">
          {/* Zero-trust summary */}
          <Card title="Zero-trust control plane" dense>
            <div className="space-y-3">
              {(posture.pillars as Json[]).map((p) => (
                <div key={p.pillar as number} className="flex items-start gap-2.5">
                  <Dot tone="ok" />
                  <div className="min-w-0">
                    <div className="text-[12px] font-medium text-ink-800">
                      Pillar {p.pillar as number} · {p.name as string}
                    </div>
                    <div className="text-[11px] text-ink-500">
                      {(p.components as Json[]).length} components active
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 pt-4 border-t border-ink-100 grid grid-cols-2 gap-4">
              <Stat
                label="Ledger entries"
                value={num(ledger.entries as number)}
                tone="blue"
                sub={ledger.chain_valid ? 'Chain verifies' : 'Chain broken'}
              />
              <Stat
                label="Row audit"
                value={audit.healthy ? 'Clean' : `${audit.tampered} flagged`}
                tone={audit.healthy ? 'ok' : 'stop'}
                mono={false}
                sub={`${audit.verified} verified`}
              />
            </div>
            <Button
              variant="secondary"
              size="sm"
              className="mt-4 w-full"
              onClick={() => onNavigate('zerotrust')}
            >
              Open the governance console
            </Button>
          </Card>

          {/* Portfolio */}
          <Card title="Portfolio" dense>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <Stat label="Claims" value={num(portfolio.total_claims as number)} />
              <Stat
                label="Settled"
                value={eur(portfolio.total_settled_eur as number, 0)}
                tone="ok"
              />
              <Stat
                label="In review"
                value={num(portfolio.in_review as number)}
                tone="warn"
              />
              <Stat
                label="Awaiting customer"
                value={num(portfolio.awaiting_customer as number)}
                tone="blue"
              />
            </div>
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-500 mb-2">
              By region
            </div>
            <div className="space-y-1.5">
              {Object.entries(portfolio.by_region as Record<string, number>)
                .filter(([k]) => k !== 'unspecified')
                .slice(0, 6)
                .map(([region, count]) => {
                  const max = Math.max(
                    ...Object.values(portfolio.by_region as Record<string, number>),
                  )
                  return (
                    <div key={region} className="flex items-center gap-2">
                      <span className="text-[11px] text-ink-600 w-[104px] truncate">{region}</span>
                      <div className="flex-1">
                        <Meter value={count / max} height={4} />
                      </div>
                      <span className="text-[11px] text-ink-500 tabular w-5 text-right">
                        {count}
                      </span>
                    </div>
                  )
                })}
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
