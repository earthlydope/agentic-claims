import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import {
  Button, Card, Chip, CopyButton, Empty, ErrorNote, Notice, Spinner, toneOf,
} from '../components/ui'
import { Avatar3D } from '../components/Avatar3D'
import { useBilingual, useDate, useLang, useMoney, useT } from '../lib/i18n'
import type { Json, Persona } from '../types'

/**
 * The customer's own claims, said the way they would want to hear it.
 *
 * There are no stages, no queues, no agent names and no scores here. A customer wants three
 * things: where is it, what do you still need from me, and how much do I get. Everything on
 * this page answers one of those, and anything that answers none of them was left off.
 */

const INCIDENT_LABEL: Record<string, [string, string]> = {
  parking_collision:  ['Parking damage', 'Parkschaden'],
  junction_collision: ['Collision at a junction', 'Kreuzungsunfall'],
  rear_end_collision: ['Rear-end collision', 'Auffahrunfall'],
  single_vehicle:     ['Single-vehicle accident', 'Alleinunfall'],
  hail:               ['Hail damage', 'Hagelschaden'],
  storm_damage:       ['Storm damage', 'Sturmschaden'],
  glass_breakage:     ['Broken glass', 'Glasbruch'],
  wild_game:          ['Collision with a wild animal', 'Wildschaden'],
  theft_attempt:      ['Theft or break-in', 'Diebstahl'],
  vandalism:          ['Vandalism', 'Vandalismus'],
  fire:               ['Fire damage', 'Brandschaden'],
  flood:              ['Flood damage', 'Hochwasserschaden'],
}

/**
 * What the customer should do next, derived from the claim's own state.
 *
 * Deliberately computed here rather than shown from a status description: a status is
 * written for the business ("awaiting_customer"), and what a person needs is an instruction
 * addressed to them.
 */
function nextStep(claim: Json, de: boolean): { text: string; act: boolean } {
  const key = ((claim.status as Json)?.key ?? '') as string
  if (key === 'awaiting_customer') {
    return {
      act: true,
      text: de
        ? 'Wir brauchen noch etwas von Ihnen. Was genau, steht in unserer Nachricht unten.'
        : 'We need something more from you. What exactly is in our message below.',
    }
  }
  if (key === 'settled' || key === 'paid' || key === 'closed') {
    return {
      act: false,
      text: de ? 'Dieser Schadensfall ist abgeschlossen.' : 'This claim is finished.',
    }
  }
  if (key === 'approved') {
    return {
      act: false,
      text: de
        ? 'Genehmigt. Die Zahlung ist unterwegs — nichts weiter zu tun.'
        : 'Approved. The payment is on its way — nothing further for you to do.',
    }
  }
  if (key === 'declined') {
    return {
      act: false,
      text: de
        ? 'Wir konnten diesen Schaden nicht übernehmen. Der Grund steht in unserer Nachricht.'
        : 'We could not cover this claim. The reason is in our message.',
    }
  }
  return {
    act: false,
    text: de
      ? 'Wir arbeiten daran. Sie müssen nichts tun — wir melden uns.'
      : 'We are working on it. Nothing for you to do — we will be in touch.',
  }
}

export function MyClaims({
  persona, onFile, onOpenClaim, refreshKey,
}: {
  persona: Persona
  onFile: () => void
  onOpenClaim: (ref: string) => void
  refreshKey: number
}) {
  const t = useT()
  const { lang } = useLang()
  const money = useMoney()
  const date = useDate()
  const say = useBilingual()
  const de = lang === 'de'
  const [data, setData] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.work(persona.key).then(setData).catch((e: Error) => setError(e.message))
  }, [persona.key])

  useEffect(() => {
    setData(null)
    load()
  }, [load, refreshKey])

  if (error) return <ErrorNote message={error} />
  if (!data) return <Spinner label={t('g.loading')} />

  const claims = (data.claims as Json[]) ?? []
  const label = (k: string) =>
    INCIDENT_LABEL[k]?.[de ? 1 : 0] ?? String(k ?? '').replace(/_/g, ' ')

  if (claims.length === 0) {
    return (
      <Card>
        <Empty action={<Button onClick={onFile}>{t('claims.report')}</Button>}>
          <span className="block text-[15px] text-ink-800 mb-1">{t('claims.none')}</span>
          {t('claims.noneHint')}
        </Empty>
      </Card>
    )
  }

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex justify-end">
        <Button onClick={onFile}>{t('claims.report')}</Button>
      </div>

      {claims.map((c) => {
        const status = (c.status as Json) ?? {}
        const step = nextStep(c, de)
        const message = c.latest_message as Json | null
        const settled = (c.settlement_amount_eur as number) > 0
        return (
          <Card key={c.reference as string}>
            {/* ── what it is ── */}
            <div className="flex items-start gap-4">
              <Avatar3D avatar="holder" accent={persona.accent} size={44} className="mt-0.5" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <h2 className="text-[16px] text-ink-900 tracking-[-0.01em]">
                    {label(c.incident_type as string)}
                  </h2>
                  <Chip tone={toneOf(status.tone as string)}>{say(status, 'label')}</Chip>
                </div>
                <p className="text-[12.5px] text-ink-600 mt-1">
                  {date(c.incident_date as string)}
                  {' · '}
                  <span className="font-mono text-[11.5px]">{c.reference as string}</span>
                </p>
              </div>
              <button
                type="button"
                onClick={() => onOpenClaim(c.reference as string)}
                className="shrink-0 text-[12.5px] text-az-700 hover:underline"
              >
                {t('claims.viewDetail')} →
              </button>
            </div>

            {/* ── what happens next: the answer they came for ── */}
            <div
              className={`mt-4 rounded-2xl px-4 py-3.5 ${
                step.act ? 'bg-warn-100' : 'bg-air'
              }`}
            >
              <div
                className={`text-[11.5px] uppercase tracking-wide ${
                  step.act ? 'text-warn-700' : 'text-az-700'
                }`}
              >
                {t('claims.whatNext')}
              </div>
              <p className="text-[13.5px] text-ink-800 mt-1 leading-relaxed">{step.text}</p>
            </div>

            {/* ── the money, only once there is a figure worth showing ── */}
            {(settled || (c.estimate_eur as number) > 0) && (
              <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3">
                {(c.estimate_eur as number) > 0 && (
                  <div>
                    <div className="text-[11.5px] text-ink-500">{t('cl.estimate')}</div>
                    <div className="text-[16px] text-ink-900 tabular mt-0.5">
                      {money(c.estimate_eur as number)}
                    </div>
                  </div>
                )}
                {(c.excess_eur as number) > 0 && (
                  <div>
                    <div className="text-[11.5px] text-ink-500">{t('claims.yourExcess')}</div>
                    <div className="text-[16px] text-ink-900 tabular mt-0.5">
                      −{money(c.excess_eur as number)}
                    </div>
                  </div>
                )}
                {settled && (
                  <div>
                    <div className="text-[11.5px] text-ink-500">{t('claims.payout')}</div>
                    <div className="text-[16px] text-ok-700 tabular mt-0.5">
                      {money(c.settlement_amount_eur as number)}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── the last thing we said, copyable ── */}
            {message && (
              <div className="mt-4 rounded-2xl bg-ink-50 px-4 py-3.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[11.5px] text-ink-500">
                      {de ? 'Unsere letzte Nachricht' : 'What we last told you'}
                    </div>
                    <div className="text-[13.5px] text-ink-900 mt-0.5">
                      {message.subject as string}
                    </div>
                  </div>
                  <CopyButton
                    text={`${message.subject as string}\n\n${message.body as string}`}
                    label={t('cl.copy')}
                    copiedLabel={t('cl.copied')}
                  />
                </div>
                <div className="mt-2.5">
                  {String(message.body ?? '')
                    .split('\n\n')
                    .map((para, i) => (
                      <p key={i} className="text-[13px] text-ink-700 leading-relaxed mb-2 last:mb-0">
                        {para}
                      </p>
                    ))}
                </div>
              </div>
            )}
          </Card>
        )
      })}

      <Notice
        tone="blue"
        title={de ? 'Sie erreichen immer einen Menschen' : 'You can always reach a person'}
      >
        {de
          ? 'Nichts hier wird von einer Maschine allein entschieden. Jede Entscheidung, die '
            + 'Ihre Auszahlung betrifft, wird von einem Menschen bestätigt — und Sie können '
            + 'jederzeit darum bitten.'
          : 'Nothing here is decided by a machine alone. Any decision that affects what you '
            + 'are paid is confirmed by a person, and you can ask for one at any point.'}
      </Notice>
    </div>
  )
}
