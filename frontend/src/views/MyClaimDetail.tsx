import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Chip, CopyButton, ErrorNote, Spinner, toneOf } from '../components/ui'
import { Avatar3D } from '../components/Avatar3D'
import { useBilingual, useDate, useLang, useMoney, useT } from '../lib/i18n'
import type { Json, Persona } from '../types'

/**
 * A customer's own claim, for a customer.
 *
 * The internal workbench had no persona gating, so a policyholder clicking "Open" on their
 * own claim was handed the run trace, the prompt-firewall verdict, the policy-guard checks
 * and — on a referred file — their own fraud score and the signals behind it. The outbound
 * guard screens customer *messages* for exactly those words; a link routed around it.
 *
 * So the customer gets this instead: what was claimed, what stage it is at in plain words,
 * what was assessed and what it means for the money, every letter we sent, and nothing
 * about how the platform reached its view.
 */

const STEP_LABELS: Record<string, [string, string]> = {
  reported:  ['Reported', 'Gemeldet'],
  assessing: ['Being assessed', 'In Prüfung'],
  decided:   ['Decision made', 'Entschieden'],
  settled:   ['Paid', 'Ausbezahlt'],
}

function Progress({ status }: { status: string }) {
  const { lang } = useLang()
  const order = ['reported', 'assessing', 'decided', 'settled']
  const reached =
    status === 'settled' || status === 'closed' ? 3
      : status === 'approved' || status === 'declined' || status === 'closed_without_payment' ? 2
        : status === 'fnol_received' ? 0
          : 1
  return (
    <ol className="flex items-center gap-2 flex-wrap">
      {order.map((key, i) => {
        const done = i <= reached
        return (
          <li key={key} className="flex items-center gap-2">
            <span
              className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                done ? 'bg-ok-600' : 'bg-ink-200'
              }`}
            />
            <span className={`text-[12.5px] ${done ? 'text-ink-800' : 'text-ink-400'}`}>
              {STEP_LABELS[key][lang === 'de' ? 1 : 0]}
            </span>
            {i < 3 && <span className="w-6 h-px bg-ink-200" />}
          </li>
        )
      })}
    </ol>
  )
}

export function MyClaimDetail({
  reference, persona, onBack,
}: {
  reference: string
  persona: Persona
  onBack: () => void
}) {
  const t = useT()
  const { lang } = useLang()
  const money = useMoney()
  const date = useDate()
  const say = useBilingual()
  const de = lang === 'de'
  const [detail, setDetail] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.claim(reference).then(setDetail).catch((e: Error) => setError(e.message))
  }, [reference])

  useEffect(() => { load() }, [load])

  if (error) return <ErrorNote message={error} />
  if (!detail) return <Spinner label={t('g.loading')} />

  const claim = (detail.claim ?? {}) as Json
  const status = (claim.status_meta ?? {}) as Json
  const cover = detail.coverage as Json | null
  const estimate = detail.estimate as Json | null
  const messages = (detail.messages ?? []) as Json[]
  const vehicle = (claim.vehicle ?? {}) as Json
  const policy = (claim.policy ?? {}) as Json
  const excess = (policy.excess_eur as number) ?? 0
  const settled = (claim.settlement_amount_eur as number) ?? 0

  return (
    <div className="max-w-3xl space-y-5">
      <button type="button" onClick={onBack}
              className="text-[12.5px] text-ink-500 hover:text-ink-800">
        ← {t('cl.back')}
      </button>

      <Card>
        <div className="flex items-start gap-4">
          <Avatar3D avatar="holder" accent={persona.accent} size={46} className="mt-0.5" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-[19px] text-ink-900 tracking-[-0.01em]">
                {vehicle.make as string} {vehicle.model as string}
              </h1>
              <Chip tone={toneOf(claim.status_tone as string)}>
                {say(status, 'label') || (claim.status as string)}
              </Chip>
            </div>
            <p className="text-[12.5px] text-ink-600 mt-1">
              {date(claim.incident_date as string)} · {claim.incident_city as string}
              {' · '}<span className="font-mono text-[11.5px]">{reference}</span>
            </p>
          </div>
        </div>

        <div className="mt-5 pt-4 border-t border-ink-100">
          <Progress status={claim.status as string} />
        </div>

        {!!claim.fnol_text && (
          <div className="mt-5 pt-4 border-t border-ink-100">
            <div className="text-[11.5px] text-ink-500 uppercase tracking-wide mb-1.5">
              {de ? 'Was Sie uns berichtet haben' : 'What you told us'}
            </div>
            <p className="text-[13px] text-ink-700 leading-relaxed italic">
              “{claim.fnol_text as string}”
            </p>
          </div>
        )}
      </Card>

      {/* What it means for the money — never a score, never a queue. */}
      {(cover || estimate || settled > 0) && (
        <Card title={de ? 'Was das für Sie bedeutet' : 'What this means for you'}>
          <div className="grid sm:grid-cols-2 gap-x-8 gap-y-4">
            {cover && (
              <div>
                <div className="text-[11.5px] text-ink-500">{t('cl.cover')}</div>
                <div className="text-[14px] text-ink-900 mt-0.5">
                  {String(cover.status).startsWith('covered')
                    ? (de ? 'Gedeckt' : 'Covered')
                    : (de ? 'Nicht gedeckt' : 'Not covered')}
                </div>
              </div>
            )}
            {!!(estimate?.total_cost as number) && (
              <div>
                <div className="text-[11.5px] text-ink-500">{t('cl.estimate')}</div>
                <div className="text-[16px] text-ink-900 tabular mt-0.5">
                  {money(estimate?.total_cost as number)}
                </div>
              </div>
            )}
            {excess > 0 && (
              <div>
                <div className="text-[11.5px] text-ink-500">{t('claims.yourExcess')}</div>
                <div className="text-[16px] text-ink-900 tabular mt-0.5">
                  −{money(excess)}
                </div>
                <div className="text-[11px] text-ink-500">{t('pol.excessHint')}</div>
              </div>
            )}
            {settled > 0 && (
              <div>
                <div className="text-[11.5px] text-ink-500">{t('claims.payout')}</div>
                <div className="text-[16px] text-ok-700 tabular mt-0.5">{money(settled)}</div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Every letter, with the copy button. */}
      {!!messages.length && (
        <Card title={de ? 'Unsere Nachrichten an Sie' : 'What we have told you'}>
          <div className="space-y-5">
            {messages
              .filter((m) => m.status !== 'blocked')
              .map((m) => (
                <div key={m.message_id as string}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[13.5px] text-ink-900">{m.subject as string}</div>
                      <div className="text-[11.5px] text-ink-500 mt-0.5">
                        {date(m.created_at as string, { withTime: true })}
                      </div>
                    </div>
                    <CopyButton
                      text={`${m.subject as string}\n\n${m.body as string}`}
                      label={t('cl.copy')}
                      copiedLabel={t('cl.copied')}
                    />
                  </div>
                  <div className="mt-2.5">
                    {String(m.body ?? '').split('\n\n').map((para, i) => (
                      <p key={i} className="text-[13px] text-ink-700 leading-relaxed mb-2 last:mb-0">
                        {para}
                      </p>
                    ))}
                  </div>
                </div>
              ))}
          </div>
        </Card>
      )}
    </div>
  )
}
