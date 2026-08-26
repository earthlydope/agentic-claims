import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import {
  Button, Card, Chip, Empty, ErrorNote, Meter, Mono, Notice, PageHeader, Segmented,
  Spinner, Stat, Table, Td,
} from '../components/ui'
import { eur, ms, num, when } from '../lib/format'
import type { Json } from '../types'

type Window = '1' | '7' | '28'

export function ModelUsage() {
  const [data, setData] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [days, setDays] = useState<Window>('28')
  const [showAll, setShowAll] = useState(false)

  const load = useCallback(() => {
    api.llmUsage(Number(days)).then(setData).catch((e: Error) => setError(e.message))
  }, [days])

  useEffect(() => {
    setData(null)
    load()
  }, [load])

  if (error) return <ErrorNote message={error} />
  if (!data) return <Spinner label="Reading model usage…" />

  const models = (data.models as Json[]) ?? []
  const totals = (data.totals as Json) ?? {}
  const shown = showAll ? models : models.filter((m) => (m.calls as number) > 0 || m.available)
  const tracing = (data.tracing as Json) ?? {}
  const chain = data.provider_chain as Json | undefined
  const byProvider = (data.by_provider as Json[]) ?? []
  const throttle = (data.throttle as Json) ?? {}
  const daily = (data.daily as Json[]) ?? []
  const maxDaily = Math.max(1, ...daily.map((d) => d.tokens as number))

  return (
    <>
      <PageHeader
        eyebrow="Observe"
        title="Model usage"
        lede="What the platform consumed, what it cost per claim, and how much headroom is left before the provider starts refusing us."
        right={
          <>
            <Segmented
              options={[
                { id: '1' as Window, label: '24 hours' },
                { id: '7' as Window, label: '7 days' },
                { id: '28' as Window, label: '28 days' },
              ]}
              value={days}
              onChange={setDays}
              size="sm"
            />
            <Button variant="secondary" size="sm" onClick={load}>
              Refresh
            </Button>
          </>
        }
      />

      {data.warning ? (
        <div className="mb-5">
          <Notice tone="stop" title="A rate limit was reached">
            {data.warning as string} A run that hits a limit stops cleanly and writes
            nothing partial. Raise the project's quota, or set{' '}
            <Mono>MODEL_RATE_LIMITS</Mono> to the quota you actually hold.
          </Notice>
        </div>
      ) : null}

      {chain ? (
        <Card
          className="mb-5"
          title="What it will try, in order"
          subtitle={chain.note as string}
          right={<Chip tone={String(chain.provider) === 'fallback' ? 'ok' : 'ghost'}>
            {String(chain.provider)}
          </Chip>}
        >
          {((chain.excluded as Json[]) ?? []).length > 0 && (
            <div className="mb-4 space-y-2">
              {((chain.excluded as Json[]) ?? []).map((x) => (
                <Notice key={x.provider as string} tone="warn"
                        title={`${String(x.provider)} is configured but not reachable`}>
                  {x.detail as string}
                  {x.remedy ? (
                    <div className="mt-1 text-ink-700">{x.remedy as string}</div>
                  ) : null}
                </Notice>
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 gap-6">
            {(['fast', 'capable'] as const).map((tier) => (
              <div key={tier}>
                <div className="text-[12px] text-ink-600 mb-2.5">{tier} tier</div>
                <div className="flex items-center gap-2 flex-wrap">
                  {((chain[tier] as Json[]) ?? []).map((leg, i) => (
                    <span key={i} className="flex items-center gap-2">
                      {i > 0 && <span className="text-ink-400 text-[13px]">→</span>}
                      <span className="inline-flex items-center gap-2 bg-ink-50 rounded-full pl-2 pr-3 py-1">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            leg.provider === 'google' ? 'bg-az-500' : 'bg-teal-600'
                          }`}
                        />
                        <Mono className="text-ink-800">{leg.model as string}</Mono>
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {((chain.legs as Json[]) ?? []).length > 0 && (
            <div className="mt-5 pt-4 border-t border-ink-100 flex flex-wrap gap-x-6 gap-y-2">
              {((chain.legs as Json[]) ?? []).map((leg) => {
                const h = leg.health as Json | null
                return (
                  <span
                    key={leg.provider as string}
                    className="flex items-center gap-2 text-[12px]"
                    title={(h?.detail as string) ?? ''}
                  >
                    <span
                      className={`w-2 h-2 rounded-full ${
                        leg.in_chain ? 'bg-ok-600' : 'bg-stop-600'
                      }`}
                    />
                    <span className="text-ink-800">{leg.label as string}</span>
                    <span className="text-ink-500">
                      {leg.in_chain ? 'in chain' : 'excluded'}
                      {h?.latency_ms ? ` · ${ms(h.latency_ms as number)}` : ''}
                    </span>
                  </span>
                )
              })}
            </div>
          )}
        </Card>
      ) : null}

      <div className="grid grid-cols-5 gap-4 mb-5">
        <Card dense>
          <Stat label="Requests" value={num(totals.calls as number)} />
        </Card>
        <Card dense>
          <Stat label="Tokens" value={num(totals.tokens as number)} />
        </Card>
        <Card dense>
          <Stat
            label="Total cost"
            value={eur(totals.metered_cost_eur as number, 4)}
            tone="blue"
            sub={
              (totals.modelled_cost_eur as number) > 0
                ? `plus ${eur(totals.modelled_cost_eur as number, 4)} modelled on the deterministic provider`
                : 'metered against the provider'
            }
          />
        </Card>
        <Card dense>
          <Stat
            label="Cost per claim"
            value={eur(totals.cost_per_claim_eur as number, 4)}
            tone="blue"
            sub={`${num(totals.claims_touched as number)} claims touched`}
          />
        </Card>
        <Card dense>
          <Stat
            label="Refused on quota"
            value={num(totals.quota_refusals as number)}
            tone={(totals.quota_refusals as number) > 0 ? 'stop' : 'ok'}
          />
        </Card>
      </div>

      {/* ── Rate limits by model — the shape Studio uses ────────── */}
      <Card
        title="Rate limits by model"
        subtitle={`Peak usage per model against its limit over the last ${data.window_days} days. A ceiling only means something against the peak — an average hides the minute you were refused.`}
        right={
          <label className="flex items-center gap-2.5 cursor-pointer">
            <span className="text-[12.5px] text-ink-600">All models</span>
            <span
              onClick={() => setShowAll((v) => !v)}
              className={`relative w-10 h-6 rounded-full transition-colors ${
                showAll ? 'bg-az-700' : 'bg-ink-300'
              }`}
            >
              <span
                className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${
                  showAll ? 'left-5' : 'left-1'
                }`}
              />
            </span>
          </label>
        }
        pad={false}
      >
        <div className="px-5 pb-5">
          <Table
            head={['Model', 'Route', 'RPM', 'TPM', 'RPD', 'Calls', 'Cost']}
          >
            {shown.map((m) => {
              const rpm = m.rpm as Json
              const tpm = m.tpm as Json
              const rpd = m.rpd as Json
              const unavailable = !m.available
              return (
                <tr key={m.model as string} className="hover:bg-ink-50/60">
                  <Td>
                    <span className="text-ink-900">{m.model as string}</span>
                    {unavailable && (
                      <Chip tone="ghost" className="ml-2">
                        not available on this key
                      </Chip>
                    )}
                    {(m.quota_refusals as number) > 0 && (
                      <Chip tone="stop" className="ml-2">
                        {String(m.quota_refusals)} refused
                      </Chip>
                    )}
                  </Td>
                  <Td>
                    <span className="flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full shrink-0 ${
                          m.provider === 'google'
                            ? 'bg-az-500'
                            : m.provider === 'openrouter'
                              ? 'bg-teal-600'
                              : 'bg-ink-300'
                        }`}
                      />
                      <span className="text-ink-700">{m.provider as string}</span>
                    </span>
                    <div className="text-[11px] text-ink-400">
                      {m.limit_source as string}
                    </div>
                  </Td>
                  <Td>
                    <QuotaBar peak={rpm.peak as number} limit={rpm.limit as number} />
                  </Td>
                  <Td>
                    <QuotaBar
                      peak={tpm.peak as number}
                      limit={tpm.limit as number}
                      compact
                    />
                  </Td>
                  <Td>
                    <QuotaBar peak={rpd.peak as number} limit={rpd.limit as number} />
                  </Td>
                  <Td align="right">{num(m.calls as number)}</Td>
                  <Td align="right">
                    {(m.calls as number) > 0 ? (
                      <>
                        {eur(m.cost_eur as number, 4)}
                        {m.cost_basis === 'modelled' && (
                          <div className="text-[10.5px] text-ink-400 font-normal">
                            modelled
                          </div>
                        )}
                      </>
                    ) : (
                      '—'
                    )}
                  </Td>
                </tr>
              )
            })}
          </Table>
          <p className="text-[12px] text-ink-500 mt-4 leading-relaxed">{data.note as string}</p>
        </div>
      </Card>

      <div className="grid grid-cols-[1fr_360px] gap-5 mt-5">
        <Card
          title="What the tokens went on"
          subtitle="A claim run, a coworker conversation and an evaluation replay all cost real money"
        >
          {((data.by_purpose as Json[]) ?? []).length === 0 ? (
            <Empty>Nothing consumed yet in this window.</Empty>
          ) : (
            <div className="space-y-3">
              {((data.by_purpose as Json[]) ?? []).map((p) => {
                const max = Math.max(
                  1,
                  ...((data.by_purpose as Json[]) ?? []).map((x) => x.tokens as number),
                )
                return (
                  <div key={p.purpose as string} className="flex items-center gap-3">
                    <span className="w-[120px] shrink-0 text-[12.5px] text-ink-700">
                      {String(p.purpose).replace(/_/g, ' ')}
                    </span>
                    <div className="flex-1">
                      <Meter value={(p.tokens as number) / max} />
                    </div>
                    <span className="w-[92px] text-right text-[12.5px] tabular text-ink-700">
                      {num(p.tokens as number)}
                    </span>
                    <span className="w-[80px] text-right text-[12.5px] tabular text-ink-600">
                      {eur(p.cost_eur as number, 4)}
                    </span>
                  </div>
                )
              })}
            </div>
          )}

          {daily.length > 1 && (
            <div className="mt-6 pt-5 border-t border-ink-100">
              <div className="text-[12px] text-ink-600 mb-3">Tokens per day</div>
              <div className="flex items-end gap-1 h-24">
                {daily.map((d) => (
                  <div
                    key={d.day as string}
                    title={`${d.day}: ${num(d.tokens as number)} tokens, ${eur(
                      d.cost_eur as number, 4,
                    )}`}
                    className="flex-1 bg-az-300 hover:bg-az-500 rounded-t-md transition-colors min-h-[2px]"
                    style={{ height: `${((d.tokens as number) / maxDaily) * 100}%` }}
                  />
                ))}
              </div>
            </div>
          )}
        </Card>

        <div className="space-y-4">
          <Card title="By provider" dense>
            {byProvider.length === 0 ? (
              <p className="text-[12.5px] text-ink-500">No calls yet.</p>
            ) : (
              <div className="space-y-3">
                {byProvider.map((p) => (
                  <div key={p.provider as string}>
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2 text-[12.5px] text-ink-800">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            String(p.provider).includes('google')
                              ? 'bg-az-500'
                              : p.provider === 'openrouter'
                                ? 'bg-teal-600'
                                : 'bg-ink-300'
                          }`}
                        />
                        {p.provider as string}
                      </span>
                      <span className="text-[13px] tabular text-ink-900">
                        {num(p.calls as number)}
                      </span>
                    </div>
                    <div className="text-[11px] text-ink-500 mt-0.5">
                      {num(p.tokens as number)} tokens
                      {(p.refusals as number) > 0 &&
                        ` · ${String(p.refusals)} refused`}
                      {(p.waited_ms as number) > 0 &&
                        ` · waited ${ms(p.waited_ms as number)}`}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {Object.keys(throttle).length > 0 && (
              <div className="mt-4 pt-3.5 border-t border-ink-100">
                <div className="text-[11.5px] text-ink-500 mb-2">
                  Limiter, per provider
                </div>
                {Object.entries(throttle as Record<string, Json>).map(([name, st]) => (
                  <div
                    key={name}
                    className="flex items-center justify-between text-[11.5px]"
                  >
                    <span className="text-ink-600">{name}</span>
                    <span className="tabular text-ink-700">
                      {String(st.max_per_minute)}/min · {String(st.waits)} waits
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Where reasoning ran" dense>
            <div className="space-y-2">
              {Object.entries((data.by_runtime as Record<string, number>) ?? {}).map(
                ([runtime, calls]) => (
                  <div key={runtime} className="flex items-center justify-between">
                    <span className="text-[12.5px] text-ink-700">{runtime}</span>
                    <span className="text-[13px] tabular text-ink-900">{num(calls)}</span>
                  </div>
                ),
              )}
              {Object.keys((data.by_runtime as Json) ?? {}).length === 0 && (
                <p className="text-[12.5px] text-ink-500">No calls yet.</p>
              )}
            </div>
          </Card>

          <Card title="Tracing" dense>
            <Chip tone={tracing.langsmith_enabled ? 'ok' : 'ghost'}>
              {tracing.destination as string}
            </Chip>
            <p className="text-[12px] text-ink-600 mt-2.5 leading-relaxed">
              {tracing.note as string}
            </p>
            {tracing.project ? (
              <div className="mt-2">
                <Mono className="text-ink-600">{tracing.project as string}</Mono>
              </div>
            ) : null}
          </Card>
        </div>
      </div>

      <Card
        className="mt-5"
        title="Recent requests"
        subtitle="Every call the platform made, with what it cost and how long it waited"
        pad={false}
      >
        <div className="px-5 pb-5">
          {((data.recent as Json[]) ?? []).length === 0 ? (
            <Empty>Nothing recorded yet. Run a claim or ask a coworker something.</Empty>
          ) : (
            <Table
              head={['When', 'Model', 'Runtime', 'Agent', 'Purpose', 'Claim', 'Tokens',
                     'Latency', 'Waited', 'Cost', '']}
            >
              {((data.recent as Json[]) ?? []).slice(0, 25).map((r, i) => (
                <tr key={i}>
                  <Td>{when(r.at as string)}</Td>
                  <Td mono>
                    <span className="flex items-center gap-1.5">
                      <span
                        className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                          r.provider === 'google'
                            ? 'bg-az-500'
                            : r.provider === 'openrouter'
                              ? 'bg-teal-600'
                              : 'bg-ink-300'
                        }`}
                      />
                      {r.model as string}
                    </span>
                  </Td>
                  <Td>{r.runtime as string}</Td>
                  <Td>{(r.agent as string) ?? '—'}</Td>
                  <Td>{String(r.purpose ?? '').replace(/_/g, ' ')}</Td>
                  <Td mono>{(r.claim_reference as string) ?? '—'}</Td>
                  <Td align="right">{num(r.total_tokens as number)}</Td>
                  <Td align="right">{ms(r.latency_ms as number)}</Td>
                  <Td align="right">
                    {(r.throttle_wait_ms as number) > 0 ? ms(r.throttle_wait_ms as number) : '—'}
                  </Td>
                  <Td align="right">{eur(r.cost_eur as number, 5)}</Td>
                  <Td>
                    {r.outcome === 'ok' ? (
                      <Chip tone="ok">ok</Chip>
                    ) : (
                      <Chip tone="stop">{r.outcome as string}</Chip>
                    )}
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      </Card>
    </>
  )
}

function QuotaBar({
  peak, limit, compact = false,
}: { peak: number; limit: number; compact?: boolean }) {
  if (!limit) {
    return <span className="text-[12px] text-ink-400">—</span>
  }
  const ratio = peak / limit
  const over = ratio >= 1
  return (
    <div className="flex items-center gap-2.5 min-w-[132px]">
      <div className="w-[52px] shrink-0">
        <Meter value={ratio} height={5} over={over} tone={ratio > 0.75 ? 'warn' : 'blue'} />
      </div>
      <span
        className={`text-[12px] tabular whitespace-nowrap ${
          over ? 'text-stop-700 font-medium' : 'text-ink-700'
        }`}
      >
        {compact ? compactNum(peak) : num(peak)} / {compact ? compactNum(limit) : num(limit)}
      </span>
    </div>
  )
}

function compactNum(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(v >= 100_000 ? 0 : 2)}K`
  return String(v)
}
