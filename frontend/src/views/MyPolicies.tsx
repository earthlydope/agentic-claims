import { useEffect, useState } from 'react'
import { api } from '../api'
import { Button, Card, Chip, Empty, ErrorNote, Spinner } from '../components/ui'
import { useDate, useLang, useMoney, useT } from '../lib/i18n'
import type { Json, Persona } from '../types'

/**
 * What a customer is covered for, said the way a customer would ask it.
 *
 * Cover on a motor policy is a list of named perils with a lot of conditions attached, and
 * a schedule reads like a schedule. So this page says the plain thing — "you are covered
 * for hail" — and puts the document one click away for anyone who wants the wording. It
 * never paraphrases the wording itself; the PDF is the wording.
 */

const COVER_LABEL: Record<string, [string, string]> = {
  collision:             ['Accident damage to your own car',
                          'Unfallschaden am eigenen Fahrzeug'],
  third_party_liability: ['Damage you cause to other people',
                          'Schäden, die Sie anderen zufügen'],
  glass:                 ['Broken glass', 'Glasbruch'],
  theft:                 ['Theft and robbery', 'Diebstahl und Raub'],
  fire:                  ['Fire and explosion', 'Brand und Explosion'],
  storm:                 ['Storm damage', 'Sturmschaden'],
  hail:                  ['Hail', 'Hagel'],
  flood:                 ['Flood and high water', 'Hochwasser und Überschwemmung'],
  wild_game:             ['Collision with wild animals', 'Wildschaden'],
  vandalism:             ['Vandalism', 'Vandalismus'],
  parking_damage:        ['Parking damage', 'Parkschaden'],
  natural_hazards:       ['Natural hazards', 'Elementarschäden'],
  snow_pressure:         ['Snow load', 'Schneedruck'],
  rockfall:              ['Rockfall and landslide', 'Steinschlag und Erdrutsch'],
  bodily_injury:         ['Injury to other people', 'Personenschäden Dritter'],
  property_damage:       ['Damage to other people’s property', 'Sachschäden Dritter'],
  legal_defence:         ['Defending claims made against you',
                          'Abwehr unbegründeter Ansprüche'],
}

/**
 * The exclusions, said as the reason a claim would be refused rather than as a category.
 *
 * "own_vehicle_damage" is the one customers on a liability-only policy are most often
 * surprised by, so it is spelled out in full rather than shortened.
 */
const EXCLUSION_LABEL: Record<string, [string, string]> = {
  own_vehicle_damage: ['Damage to your own car — this policy covers other people’s',
                       'Schaden am eigenen Fahrzeug — diese Polizze deckt fremde Schäden'],
  at_fault_collision: ['An accident that was your fault',
                       'Unfall, den Sie selbst verschuldet haben'],
  intent:             ['Damage caused on purpose', 'Vorsätzlich verursachte Schäden'],
  intoxication:       ['Driving under the influence of alcohol or drugs',
                       'Fahren unter Alkohol- oder Drogeneinfluss'],
  unlicensed:         ['Driving without a valid licence',
                       'Fahren ohne gültige Lenkerberechtigung'],
  glass:              ['Broken glass', 'Glasbruch'],
  wear_and_tear:      ['Wear and tear', 'Abnutzung und Verschleiß'],
  mechanical:         ['Mechanical or brake damage, and pure breakage',
                       'Brems-, Betriebs- und reine Bruchschäden'],
  motorsport:         ['Motorsport and track use', 'Motorsport und Rennveranstaltungen'],
  collision:          ['Accident damage to your own car',
                       'Unfallschaden am eigenen Fahrzeug'],
  vandalism:          ['Vandalism', 'Vandalismus'],
  theft:              ['Theft', 'Diebstahl'],
  war_riot:           ['War, civil unrest and earthquake',
                       'Krieg, innere Unruhen und Erdbeben'],
  radiation:          ['Ionising radiation', 'Ionisierende Strahlung'],
}

function useLabel(map: Record<string, [string, string]>) {
  const { lang } = useLang()
  return (key: string) => {
    const row = map[key]
    if (!row) return key.replace(/_/g, ' ')
    return row[lang === 'de' ? 1 : 0]
  }
}

/** A tick or a cross, so cover reads at a glance rather than being read. */
function CoverRow({ label, on }: { label: string; on: boolean }) {
  return (
    <li className="flex items-start gap-2.5 text-[13px] leading-relaxed">
      <span
        className={`mt-[3px] shrink-0 w-[18px] h-[18px] rounded-full flex items-center
                    justify-center ${on ? 'bg-ok-100 text-ok-700' : 'bg-ink-100 text-ink-500'}`}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6"
             strokeLinecap="round" strokeLinejoin="round" className="w-2.5 h-2.5">
          {on ? <path d="m4 12.5 5 5L20 6.5" /> : <path d="M6 6l12 12M18 6L6 18" />}
        </svg>
      </span>
      <span className={on ? 'text-ink-800' : 'text-ink-500'}>{label}</span>
    </li>
  )
}

export function MyPolicies({
  persona,
  onClaimOn,
  onOpenClaim,
  refreshKey,
}: {
  persona: Persona
  onClaimOn: (policyNumber: string) => void
  onOpenClaim: (reference: string) => void
  refreshKey?: number
}) {
  const t = useT()
  const { lang } = useLang()
  const money = useMoney()
  const date = useDate()
  const coverLabel = useLabel(COVER_LABEL)
  const exclusionLabel = useLabel(EXCLUSION_LABEL)
  const [data, setData] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setData(null)
    api
      .myPolicies(persona.key)
      .then(setData)
      .catch((e: Error) => setError(e.message))
  }, [persona.key, refreshKey])

  if (error) return <ErrorNote message={error} />
  if (!data) return <Spinner label={t('g.loading')} />

  const policies = (data.policies ?? []) as Json[]
  if (!policies.length) {
    return <Card><Empty>{t('pol.none')}</Empty></Card>
  }

  return (
    <div className="space-y-5">
      {policies.map((p) => {
        const v = (p.vehicle ?? {}) as Json
        const doc = p.document as Json | null
        const active = p.status === 'active'
        const covers = (p.covers ?? []) as string[]
        const exclusions = (p.exclusions ?? []) as string[]
        const endorsements = (p.endorsements ?? []) as Json[]
        const openClaims = (p.open_claims ?? []) as string[]

        return (
          <Card key={p.policy_number} className="overflow-visible">
            {/* ── the vehicle, which is how a customer identifies the policy ── */}
            <div className="flex flex-wrap items-start justify-between gap-4 pb-4
                            border-b border-ink-100">
              <div className="min-w-0">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <h2 className="text-[17px] text-ink-900 tracking-[-0.01em]">
                    {v.make} {v.model}
                  </h2>
                  <Chip tone="ghost" mono>{v.plate}</Chip>
                  <Chip tone={active ? 'ok' : 'neutral'}>
                    {active ? t('pol.active') : t('pol.lapsed')}
                  </Chip>
                </div>
                <p className="text-[12.5px] text-ink-600 mt-1.5">
                  {p.product_label} · {v.year} · {t('pol.since')} {date(p.inception_date)}
                  {' · '}
                  <span className="font-mono text-[11.5px]">{p.policy_number}</span>
                </p>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {doc && (
                  <>
                    <a
                      href={`/api${(doc.url as string).replace('/api', '')}?persona=${persona.key}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full
                                 border border-ink-200 text-[12.5px] text-ink-700
                                 hover:bg-ink-50 transition-colors"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                           strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
                           className="w-4 h-4">
                        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                      {t('pol.view')}
                    </a>
                    <a
                      href={`/api${(doc.url as string).replace('/api', '')}?persona=${persona.key}`}
                      download={doc.filename as string}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full
                                 border border-ink-200 text-[12.5px] text-ink-700
                                 hover:bg-ink-50 transition-colors"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                           strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
                           className="w-4 h-4">
                        <path d="M12 3v12m0 0-4.5-4.5M12 15l4.5-4.5M4 19h16" />
                      </svg>
                      {t('pol.download')}
                    </a>
                  </>
                )}
                {active && (
                  <Button onClick={() => onClaimOn(p.policy_number as string)}>
                    {t('pol.claimOnThis')}
                  </Button>
                )}
              </div>
            </div>

            {/* ── the three numbers that actually matter to a customer ── */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-4 py-4
                            border-b border-ink-100">
              <div>
                <div className="text-[11.5px] text-ink-500">{t('pol.premium')}</div>
                <div className="text-[17px] text-ink-900 tabular mt-0.5">
                  {money(p.annual_premium_eur as number)}
                </div>
                <div className="text-[11px] text-ink-500">{t('pol.perYear')}</div>
              </div>
              <div>
                <div className="text-[11.5px] text-ink-500">{t('pol.excess')}</div>
                <div className="text-[17px] text-ink-900 tabular mt-0.5">
                  {money(p.excess_eur as number)}
                </div>
                <div className="text-[11px] text-ink-500">{t('pol.excessHint')}</div>
              </div>
              <div>
                <div className="text-[11.5px] text-ink-500">{t('pol.sumInsured')}</div>
                <div className="text-[17px] text-ink-900 tabular mt-0.5">
                  {money((p.sum_insured_eur as number) || (v.market_value_eur as number))}
                </div>
                <div className="text-[11px] text-ink-500">
                  {t('pol.renews')} {date(p.renewal_date)}
                </div>
              </div>
              <div>
                <div className="text-[11.5px] text-ink-500">{t('pol.ncd')}</div>
                <div className="text-[17px] text-ink-900 tabular mt-0.5">
                  {p.no_claims_years as number}
                </div>
                {(p.protected_ncd as boolean) && (
                  <div className="text-[11px] text-ok-700">{t('pol.ncdProtected')}</div>
                )}
              </div>
            </div>

            {/* ── cover, in and out ── */}
            <div className="grid md:grid-cols-2 gap-x-8 gap-y-5 pt-4">
              <div>
                <div className="text-[12px] text-ink-700 font-medium mb-2.5">
                  {t('pol.covered')}
                </div>
                <ul className="space-y-1.5">
                  {covers.map((c) => (
                    <CoverRow key={c} label={coverLabel(c)} on />
                  ))}
                </ul>
                {!!endorsements.length && (
                  <div className="mt-4">
                    <div className="text-[12px] text-ink-700 font-medium mb-2">
                      {t('pol.extras')}
                    </div>
                    <ul className="space-y-1.5">
                      {endorsements.map((e) => (
                        <li key={e.code as string}
                            className="text-[12.5px] text-ink-700 leading-relaxed">
                          {(lang === 'de' && (e.label_de as string)) || (e.label as string)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              <div>
                {!!exclusions.length && (
                  <>
                    <div className="text-[12px] text-ink-700 font-medium mb-2.5">
                      {t('pol.notCovered')}
                    </div>
                    <ul className="space-y-1.5">
                      {exclusions.map((c) => (
                        <CoverRow key={c} label={exclusionLabel(c)} on={false} />
                      ))}
                    </ul>
                  </>
                )}

                {!!openClaims.length && (
                  <div className="mt-5 rounded-2xl bg-air px-4 py-3">
                    <div className="text-[11.5px] text-az-700 uppercase tracking-wide">
                      {t('pol.openClaim')}
                    </div>
                    <div className="flex flex-wrap gap-2 mt-2">
                      {openClaims.map((ref) => (
                        <button
                          key={ref}
                          type="button"
                          onClick={() => onOpenClaim(ref)}
                          className="font-mono text-[12px] text-az-700 underline
                                     decoration-az-300 hover:decoration-az-700"
                        >
                          {ref}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Card>
        )
      })}
    </div>
  )
}
