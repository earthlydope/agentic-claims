import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Button, Card, Chip, ErrorNote, Spinner } from '../components/ui'
import { Avatar3D } from '../components/Avatar3D'
import { useDate, useLang, useMoney, useT } from '../lib/i18n'
import type { Json, Persona } from '../types'

/**
 * Reporting a claim, the way it happens rather than the way it is stored.
 *
 * Three decisions shape this screen. The customer picks a car, not a policy number, because
 * that is how they know which policy they mean. They choose between telling us what happened
 * in a conversation and filling in a form, because both kinds of people exist and forcing
 * either one is how claims get abandoned half-finished. And nothing here mentions a stage, a
 * queue, a model or a run — the analysis starts on its own the moment they press submit, and
 * what they see afterwards is a claim that is already moving.
 */

type Step = 'vehicle' | 'story' | 'evidence' | 'filed'
type Route = 'guided' | 'form'

interface Turn { question: string; answer: string }

const REGIONS = [
  'Wien', 'Niederösterreich', 'Oberösterreich', 'Steiermark', 'Salzburg', 'Tirol',
  'Vorarlberg', 'Kärnten', 'Burgenland',
]

const INCIDENT_LABEL: Record<string, [string, string]> = {
  parking_collision:  ['Hit something while parking or manoeuvring', 'Park- oder Rangierschaden'],
  junction_collision: ['Collision at a junction', 'Kreuzungsunfall'],
  rear_end_collision: ['Someone drove into the back of me', 'Auffahrunfall'],
  single_vehicle:     ['I was on my own — no other vehicle', 'Alleinunfall'],
  hail:               ['Hail', 'Hagelschaden'],
  storm_damage:       ['Storm', 'Sturmschaden'],
  glass_breakage:     ['Broken glass', 'Glasbruch'],
  wild_game:          ['Collision with a wild animal', 'Wildschaden'],
  theft_attempt:      ['Theft or break-in', 'Diebstahl oder Einbruch'],
  vandalism:          ['Vandalism', 'Vandalismus'],
  flood:              ['Flood or high water', 'Hochwasser'],
}

/** The rail across the top. Three steps, so it never feels open-ended. */
function Steps({ step }: { step: Step }) {
  const t = useT()
  const order: Step[] = ['vehicle', 'story', 'evidence']
  const at = order.indexOf(step)
  const labels = [t('file.step1'), t('file.step2'), t('file.step3')]
  return (
    <ol className="flex items-center gap-2 mb-6">
      {order.map((s, i) => {
        const done = at > i || step === 'filed'
        const on = at === i
        return (
          <li key={s} className="flex items-center gap-2">
            <span
              className={`w-6 h-6 rounded-full flex items-center justify-center text-[11.5px]
                          font-medium shrink-0 ${
                done ? 'bg-ok-600 text-white'
                  : on ? 'bg-az-700 text-white' : 'bg-ink-100 text-ink-500'
              }`}
            >
              {done ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
                     strokeLinecap="round" className="w-3 h-3"><path d="m4 12.5 5 5L20 6.5" /></svg>
              ) : i + 1}
            </span>
            <span className={`text-[12.5px] ${on ? 'text-ink-900' : 'text-ink-500'}`}>
              {labels[i]}
            </span>
            {i < 2 && <span className="w-8 h-px bg-ink-200 mx-1" />}
          </li>
        )
      })}
    </ol>
  )
}

export function FileClaim({
  persona,
  presetPolicy,
  onOpenClaim,
}: {
  persona: Persona
  presetPolicy?: string
  onOpenClaim: (ref: string) => void
}) {
  const t = useT()
  const { lang } = useLang()
  const money = useMoney()
  const date = useDate()

  const [step, setStep] = useState<Step>('vehicle')
  const [policies, setPolicies] = useState<Json[] | null>(null)
  const [policy, setPolicy] = useState(presetPolicy ?? '')
  const [route, setRoute] = useState<Route | null>(null)
  const [error, setError] = useState<string | null>(null)

  // guided
  const [turns, setTurns] = useState<Turn[]>([])
  const [ask, setAsk] = useState<Json | null>(null)
  const [reply, setReply] = useState('')
  const [asking, setAsking] = useState(false)
  const feed = useRef<HTMLDivElement>(null)

  // form
  const [story, setStory] = useState('')
  const [when, setWhen] = useState(() => new Date().toISOString().slice(0, 10))
  const [kind, setKind] = useState('parking_collision')
  const [region, setRegion] = useState('Wien')
  const [city, setCity] = useState('')
  const [injury, setInjury] = useState(false)
  const [thirdParty, setThirdParty] = useState(false)

  // evidence + result
  const [files, setFiles] = useState<File[]>([])
  const [samples, setSamples] = useState<Json[] | null>(null)
  const [dragging, setDragging] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [filed, setFiled] = useState<Json | null>(null)
  const [working, setWorking] = useState(false)

  useEffect(() => {
    api.myPolicies(persona.key)
      .then((d) => {
        const rows = ((d as Json).policies ?? []) as Json[]
        setPolicies(rows)
        if (!policy && rows.length === 1) setPolicy(rows[0].policy_number as string)
      })
      .catch((e: Error) => setError(e.message))
    api.testDocuments().then((d) => setSamples(((d as Json).documents ?? []) as Json[]))
      .catch(() => setSamples([]))
  }, [persona.key])   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (feed.current) feed.current.scrollTop = feed.current.scrollHeight
  }, [turns, ask, asking])

  const nextQuestion = useCallback(
    async (history: Turn[]) => {
      setAsking(true)
      try {
        const r = (await api.intakeQuestion(policy, history, lang)) as Json
        setAsk(r)
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setAsking(false)
      }
    },
    [policy, lang],
  )

  // Starting the conversation is what choosing "answer a few questions" means.
  const startGuided = () => {
    setRoute('guided')
    setStep('story')
    setTurns([])
    setAsk(null)
    void nextQuestion([])
  }

  const answer = async (text: string) => {
    const said = text.trim()
    if (!said || asking || !ask) return
    const history = [...turns, { question: ask.question as string, answer: said }]
    setTurns(history)
    setReply('')
    await nextQuestion(history)
  }

  const addFiles = (incoming: FileList | File[]) => {
    const next = Array.from(incoming)
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`))
      return [...prev, ...next.filter((f) => !seen.has(`${f.name}:${f.size}`))].slice(0, 12)
    })
  }

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      let draft: Json
      if (route === 'guided') {
        draft = (await api.intakeAssemble(turns, lang)) as Json
      } else {
        draft = {
          fnol_text: story,
          incident_date: when,
          incident_type: kind,
          incident_region: region,
          incident_city: city || region,
          injury_reported: injury,
          third_party_involved: thirdParty,
          language: lang,
        }
      }

      const form = new FormData()
      form.set('policy_number', policy)
      form.set('fnol_text', String(draft.fnol_text ?? story))
      form.set('incident_date', String(draft.incident_date ?? when))
      form.set('incident_type', String(draft.incident_type ?? kind))
      form.set('incident_region', String(draft.incident_region ?? region))
      form.set('incident_city', String(draft.incident_city ?? city ?? region))
      form.set('language', String(draft.language ?? lang))
      form.set('injury_reported', String(Boolean(draft.injury_reported ?? injury)))
      form.set('third_party_involved',
               String(Boolean(draft.third_party_involved ?? thirdParty)))
      for (const f of files) form.append('files', f)

      const result = (await api.intakeUpload(form)) as Json
      if (result.accepted === false) {
        setError(String((result.reason as string) ?? 'That notification was not accepted.'))
        return
      }
      setFiled({ ...result, draft })
      setStep('filed')
      setWorking(true)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  // Once it is filed, the work has already started. Poll quietly until it stops.
  useEffect(() => {
    if (!filed?.reference || !working) return
    let alive = true
    const tick = async () => {
      try {
        const s = (await api.analysisState(filed.reference as string)) as Json
        if (!alive) return
        if (!s.working) { setWorking(false); return }
      } catch {
        if (alive) setWorking(false)
        return
      }
      if (alive) window.setTimeout(tick, 4000)
    }
    const id = window.setTimeout(tick, 3000)
    return () => { alive = false; window.clearTimeout(id) }
  }, [filed, working])

  if (error && !policies) return <ErrorNote message={error} />
  if (!policies) return <Spinner label={t('g.loading')} />

  const chosen = policies.find((p) => p.policy_number === policy)
  const label = (k: string) => (INCIDENT_LABEL[k]?.[lang === 'de' ? 1 : 0]) ?? k

  // ── filed ──────────────────────────────────────────────────────────
  if (step === 'filed' && filed) {
    const derived = (filed.derived ?? {}) as Json
    const needs = (derived.needs_confirming ?? []) as Json[]
    return (
      <div className="max-w-2xl">
        <Card>
          <div className="text-center py-4">
            <span className="inline-flex items-center justify-center w-14 h-14 rounded-full
                             bg-ok-100 text-ok-700 mb-4">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
                   strokeLinecap="round" strokeLinejoin="round" className="w-7 h-7">
                <path d="m4 12.5 5 5L20 6.5" />
              </svg>
            </span>
            <h2 className="text-[19px] text-ink-900 tracking-[-0.01em]">{t('file.thanks')}</h2>
            <p className="text-[13px] text-ink-600 mt-2">{t('file.weWillWrite')}</p>

            <div className="mt-5 inline-flex flex-col items-center gap-1 px-6 py-4
                            rounded-2xl bg-ink-50">
              <span className="text-[11.5px] text-ink-500 uppercase tracking-wide">
                {t('file.reference')}
              </span>
              <span className="font-mono text-[17px] text-ink-900">
                {filed.reference as string}
              </span>
            </div>

            {working && (
              <div className="mt-5 flex items-center justify-center gap-2.5 text-[13px]
                              text-az-700">
                <span className="inline-block w-3.5 h-3.5 border-2 border-az-500
                                 border-t-transparent rounded-full animate-spin" />
                {t('file.reviewing')}
              </div>
            )}
            {!working && (
              <p className="mt-5 text-[12.5px] text-ink-600">{t('cl.autoStarted')}</p>
            )}

            {!!needs.length && (
              <div className="mt-5 text-left rounded-2xl bg-warn-100 px-4 py-3">
                <div className="text-[12px] text-warn-700">
                  {lang === 'de'
                    ? 'Wir möchten zwei Angaben mit Ihnen bestätigen:'
                    : 'We would like to confirm two things with you:'}
                </div>
                <ul className="mt-1.5 space-y-1">
                  {needs.slice(0, 3).map((n, i) => (
                    <li key={i} className="text-[12.5px] text-ink-700">
                      {String(n.field)} — {lang === 'de' ? 'gelesen als' : 'read as'}{' '}
                      <span className="font-mono">{String(n.read_as)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-6 flex items-center justify-center gap-2.5">
              <Button onClick={() => onOpenClaim(filed.reference as string)}>
                {t('file.followIt')}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="max-w-3xl">
      <Steps step={step} />
      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      {/* ── 1. which vehicle ──────────────────────────────────────── */}
      {step === 'vehicle' && (
        <Card title={t('file.step1')} subtitle={t('file.pickPolicy')}>
          <div className="space-y-2.5">
            {policies.map((p) => {
              const v = (p.vehicle ?? {}) as Json
              const on = p.policy_number === policy
              const claimable = p.can_claim as boolean
              return (
                <button
                  key={p.policy_number as string}
                  type="button"
                  disabled={!claimable}
                  onClick={() => setPolicy(p.policy_number as string)}
                  className={`w-full text-left flex items-center gap-4 px-4 py-3.5 rounded-2xl
                              border transition-all disabled:opacity-50
                              disabled:cursor-not-allowed ${
                    on ? 'border-az-500 bg-air ring-1 ring-az-500'
                       : 'border-ink-200 hover:border-ink-300 hover:bg-ink-50'
                  }`}
                >
                  <Avatar3D avatar="holder" accent={on ? 'blue' : 'slate'} size={46} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2 flex-wrap">
                      <span className="text-[14.5px] text-ink-900">
                        {v.make as string} {v.model as string}
                      </span>
                      <Chip tone="ghost" mono>{v.plate as string}</Chip>
                    </span>
                    <span className="block text-[12px] text-ink-600 mt-0.5">
                      {p.product_label as string} · {t('pol.excess')} {money(p.excess_eur as number)}
                    </span>
                  </span>
                  <span
                    className={`w-5 h-5 rounded-full border-2 shrink-0 flex items-center
                                justify-center ${on ? 'border-az-600 bg-az-600' : 'border-ink-300'}`}
                  >
                    {on && <span className="w-1.5 h-1.5 rounded-full bg-white" />}
                  </span>
                </button>
              )
            })}
          </div>

          <div className="mt-5 pt-4 border-t border-ink-100">
            <div className="text-[12.5px] text-ink-700">{t('file.orUpload')}</div>
            <p className="text-[12px] text-ink-500 mt-1 leading-relaxed">
              {t('file.uploadPolicyHint')}
            </p>
            <label className="inline-flex items-center gap-2 mt-2.5 px-3.5 py-2 rounded-full
                              border border-ink-200 text-[12.5px] text-ink-700 cursor-pointer
                              hover:bg-ink-50">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
                   strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
                <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M4 19h16" />
              </svg>
              {t('pol.document')}
              <input
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => { if (e.target.files) addFiles(e.target.files) }}
              />
            </label>
            {files.some((f) => f.type === 'application/pdf') && (
              <div className="mt-2 text-[12px] text-ok-700">
                {files.filter((f) => f.type === 'application/pdf').map((f) => f.name).join(', ')}
              </div>
            )}
          </div>

          <div className="mt-6 flex items-center gap-2.5">
            <Button disabled={!policy} onClick={() => setStep('story')}>
              {t('file.next')}
            </Button>
          </div>
        </Card>
      )}

      {/* ── 2. what happened ─────────────────────────────────────── */}
      {step === 'story' && (
        <>
          {!route && (
            <Card title={t('file.step2')}>
              <div className="grid sm:grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={startGuided}
                  className="text-left p-5 rounded-2xl border border-ink-200 hover:border-az-400
                             hover:bg-az-50 transition-all group"
                >
                  <span className="inline-flex items-center justify-center w-10 h-10 rounded-full
                                   bg-air text-az-700 mb-3">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                         strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
                      <path d="M21 12a8 8 0 0 1-8 8H8l-4 3v-4a8 8 0 0 1 8-11h1a8 8 0 0 1 8 4z" />
                    </svg>
                  </span>
                  <span className="block text-[14px] text-ink-900">
                    {t('file.answerQuestions')}
                  </span>
                  <span className="block text-[12.5px] text-ink-600 mt-1 leading-relaxed">
                    {t('file.questionsHint')}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => { setRoute('form'); setStep('story') }}
                  className="text-left p-5 rounded-2xl border border-ink-200 hover:border-az-400
                             hover:bg-az-50 transition-all"
                >
                  <span className="inline-flex items-center justify-center w-10 h-10 rounded-full
                                   bg-ink-100 text-ink-700 mb-3">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                         strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
                      <path d="M6 3h9l4 4v14H6zM9 12h7M9 16h5M9 8h4" />
                    </svg>
                  </span>
                  <span className="block text-[14px] text-ink-900">{t('file.fillForm')}</span>
                  <span className="block text-[12.5px] text-ink-600 mt-1 leading-relaxed">
                    {t('file.formHint')}
                  </span>
                </button>
              </div>
              <div className="mt-5">
                <button type="button" onClick={() => setStep('vehicle')}
                        className="text-[12.5px] text-ink-500 hover:text-ink-800">
                  ← {t('file.back')}
                </button>
              </div>
            </Card>
          )}

          {/* the conversation */}
          {route === 'guided' && (
            <Card
              title={t('file.step2')}
              right={
                <button type="button" onClick={() => setRoute('form')}
                        className="text-[12px] text-az-700 hover:underline">
                  {t('q.switchToForm')}
                </button>
              }
            >
              <div ref={feed} className="space-y-3 max-h-[46vh] overflow-y-auto pr-1">
                {turns.map((turn, i) => (
                  <div key={i} className="space-y-2">
                    <div className="flex gap-2.5">
                      <Avatar3D avatar="handler" accent="blue" size={26} className="mt-0.5" />
                      <div className="px-3.5 py-2.5 rounded-2xl rounded-tl-md bg-ink-50
                                      text-[13px] text-ink-800 leading-relaxed max-w-[85%]">
                        {turn.question}
                      </div>
                    </div>
                    <div className="flex justify-end">
                      <div className="px-3.5 py-2.5 rounded-2xl rounded-br-md bg-az-600
                                      text-white text-[13px] leading-relaxed max-w-[85%]">
                        {turn.answer}
                      </div>
                    </div>
                  </div>
                ))}

                {asking && (
                  <div className="flex gap-2.5 items-center">
                    <Avatar3D avatar="handler" accent="blue" size={26} />
                    <div className="px-3.5 py-3 rounded-2xl rounded-tl-md bg-ink-50 flex gap-1">
                      {[0, 1, 2].map((i) => (
                        <span key={i} className="w-1.5 h-1.5 rounded-full bg-ink-400 animate-bounce"
                              style={{ animationDelay: `${i * 0.14}s` }} />
                      ))}
                    </div>
                  </div>
                )}

                {!asking && ask && !ask.done && (
                  <div className="flex gap-2.5">
                    <Avatar3D avatar="handler" accent="blue" size={26} className="mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <div className={`px-3.5 py-2.5 rounded-2xl rounded-tl-md text-[13px]
                                       leading-relaxed ${
                        ask.blocked ? 'bg-warn-100 text-warn-700' : 'bg-ink-50 text-ink-800'
                      }`}>
                        {ask.question as string}
                        {!!ask.why && (
                          <span className="block text-[11.5px] text-ink-500 mt-1">
                            {ask.why as string}
                          </span>
                        )}
                      </div>
                      {!!(ask.examples as string[])?.length && (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                          {(ask.examples as string[]).map((ex) => (
                            <button key={ex} type="button" onClick={() => void answer(ex)}
                                    className="px-3 py-1.5 rounded-full bg-white border
                                               border-ink-200 text-[12px] text-ink-700
                                               hover:border-az-400 hover:text-az-700">
                              {ex}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {!asking && ask?.done && (
                  <div className="flex items-center gap-2 text-[13px] text-ok-700 pt-1">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
                         strokeLinecap="round" className="w-4 h-4">
                      <path d="m4 12.5 5 5L20 6.5" />
                    </svg>
                    {t('q.done')}
                  </div>
                )}
              </div>

              {!ask?.done && (
                <div className="flex items-end gap-2 bg-ink-50 rounded-2xl px-3 py-2 mt-4">
                  <textarea
                    rows={1}
                    value={reply}
                    onChange={(e) => {
                      setReply(e.target.value)
                      e.target.style.height = 'auto'
                      e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void answer(reply) }
                    }}
                    placeholder={t('q.yourAnswer')}
                    className="flex-1 bg-transparent resize-none text-[13px] text-ink-900
                               placeholder:text-ink-400 outline-none leading-relaxed py-1"
                  />
                  <button
                    type="button"
                    onClick={() => void answer(reply)}
                    disabled={asking || !reply.trim()}
                    className="shrink-0 w-8 h-8 rounded-full bg-az-600 text-white flex items-center
                               justify-center disabled:opacity-30 hover:bg-az-700"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                         strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
                      <path d="M5 12h13M12 5l7 7-7 7" />
                    </svg>
                  </button>
                </div>
              )}

              <div className="mt-5 flex items-center gap-2.5">
                <Button disabled={!ask?.done} onClick={() => setStep('evidence')}>
                  {t('file.next')}
                </Button>
                <button type="button" onClick={() => { setRoute(null); setAsk(null) }}
                        className="text-[12.5px] text-ink-500 hover:text-ink-800">
                  ← {t('file.back')}
                </button>
              </div>
            </Card>
          )}

          {/* the form */}
          {route === 'form' && (
            <Card
              title={t('file.step2')}
              right={
                <button type="button" onClick={startGuided}
                        className="text-[12px] text-az-700 hover:underline">
                  {t('file.answerQuestions')}
                </button>
              }
            >
              <div className="space-y-4">
                <div>
                  <label className="block text-[12.5px] text-ink-700 mb-1.5">
                    {t('file.freeText')}
                  </label>
                  <textarea
                    rows={4}
                    value={story}
                    onChange={(e) => setStory(e.target.value)}
                    placeholder={t('file.freeTextPlaceholder')}
                    className="w-full rounded-2xl border border-ink-200 px-4 py-3 text-[13px]
                               text-ink-900 placeholder:text-ink-400 outline-none
                               focus:border-az-500 focus:ring-1 focus:ring-az-500
                               leading-relaxed resize-y"
                  />
                </div>

                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[12.5px] text-ink-700 mb-1.5">
                      {lang === 'de' ? 'Wann?' : 'When?'}
                    </label>
                    <input
                      type="date"
                      value={when}
                      max={new Date().toISOString().slice(0, 10)}
                      onChange={(e) => setWhen(e.target.value)}
                      className="w-full rounded-full border border-ink-200 px-4 py-2.5
                                 text-[13px] outline-none focus:border-az-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[12.5px] text-ink-700 mb-1.5">
                      {lang === 'de' ? 'Was ist passiert?' : 'What kind of incident?'}
                    </label>
                    <select
                      value={kind}
                      onChange={(e) => setKind(e.target.value)}
                      className="w-full rounded-full border border-ink-200 px-4 py-2.5
                                 text-[13px] outline-none focus:border-az-500 bg-white"
                    >
                      {Object.keys(INCIDENT_LABEL).map((k) => (
                        <option key={k} value={k}>{label(k)}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[12.5px] text-ink-700 mb-1.5">
                      {lang === 'de' ? 'Bundesland' : 'Which part of Austria?'}
                    </label>
                    <select
                      value={region}
                      onChange={(e) => setRegion(e.target.value)}
                      className="w-full rounded-full border border-ink-200 px-4 py-2.5
                                 text-[13px] outline-none focus:border-az-500 bg-white"
                    >
                      {REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[12.5px] text-ink-700 mb-1.5">
                      {lang === 'de' ? 'Ort' : 'Town or city'}
                    </label>
                    <input
                      value={city}
                      onChange={(e) => setCity(e.target.value)}
                      placeholder={region}
                      className="w-full rounded-full border border-ink-200 px-4 py-2.5
                                 text-[13px] outline-none focus:border-az-500
                                 placeholder:text-ink-400"
                    />
                  </div>
                </div>

                <div className="flex flex-wrap gap-5 pt-1">
                  {[
                    { on: injury, set: setInjury,
                      label: lang === 'de' ? 'Es wurde jemand verletzt' : 'Someone was hurt' },
                    { on: thirdParty, set: setThirdParty,
                      label: lang === 'de' ? 'Ein anderes Fahrzeug war beteiligt'
                                           : 'Another vehicle was involved' },
                  ].map((row) => (
                    <label key={row.label} className="flex items-center gap-2.5 cursor-pointer">
                      <input type="checkbox" checked={row.on}
                             onChange={(e) => row.set(e.target.checked)}
                             className="w-4 h-4 rounded accent-az-600" />
                      <span className="text-[13px] text-ink-700">{row.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="mt-6 flex items-center gap-2.5">
                <Button disabled={story.trim().length < 12} onClick={() => setStep('evidence')}>
                  {t('file.next')}
                </Button>
                <button type="button" onClick={() => setRoute(null)}
                        className="text-[12.5px] text-ink-500 hover:text-ink-800">
                  ← {t('file.back')}
                </button>
              </div>
            </Card>
          )}
        </>
      )}

      {/* ── 3. anything to attach ────────────────────────────────── */}
      {step === 'evidence' && (
        <Card title={t('file.step3')} subtitle={t('file.attachHint')}>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              if (e.dataTransfer.files) addFiles(e.dataTransfer.files)
            }}
            className={`rounded-2xl border-2 border-dashed px-6 py-9 text-center transition-colors ${
              dragging ? 'border-az-500 bg-air' : 'border-ink-200'
            }`}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
                 strokeLinecap="round" strokeLinejoin="round"
                 className="w-8 h-8 mx-auto text-ink-400 mb-3">
              <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M4 19h16" />
            </svg>
            <p className="text-[13px] text-ink-700">
              {t('file.drop')}{' '}
              <label className="text-az-700 underline cursor-pointer">
                {t('file.browse')}
                <input type="file" multiple className="hidden"
                       accept="application/pdf,image/*"
                       onChange={(e) => { if (e.target.files) addFiles(e.target.files) }} />
              </label>
            </p>
            <p className="text-[12px] text-ink-500 mt-1.5">{t('file.attach')}</p>
          </div>

          {!!files.length && (
            <ul className="mt-4 space-y-1.5">
              {files.map((f, i) => (
                <li key={`${f.name}-${i}`}
                    className="flex items-center gap-3 px-3.5 py-2.5 rounded-xl bg-ink-50">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
                       className="w-4 h-4 text-ink-500 shrink-0" strokeLinecap="round">
                    <path d="M6 3h9l4 4v14H6z" />
                  </svg>
                  <span className="text-[12.5px] text-ink-800 truncate flex-1">{f.name}</span>
                  <span className="text-[11.5px] text-ink-500 tabular shrink-0">
                    {(f.size / 1024).toFixed(0)} KB
                  </span>
                  <button type="button"
                          onClick={() => setFiles((p) => p.filter((_, j) => j !== i))}
                          className="text-ink-400 hover:text-stop-600 shrink-0">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                         strokeLinecap="round" className="w-4 h-4">
                      <path d="M6 6l12 12M18 6L6 18" />
                    </svg>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {!!samples?.length && (
            <details className="mt-5">
              <summary className="text-[12px] text-ink-500 cursor-pointer hover:text-ink-800">
                {lang === 'de' ? 'Beispieldokumente zum Testen' : 'Sample documents for testing'}
              </summary>
              <div className="flex flex-wrap gap-1.5 mt-2.5">
                {samples.map((d) => (
                  <button
                    key={d.filename as string}
                    type="button"
                    onClick={async () => {
                      try {
                        addFiles([await api.fetchTestDocument(d.filename as string,
                                                              d.mime_type as string)])
                      } catch (e) { setError((e as Error).message) }
                    }}
                    className="px-3 py-1.5 rounded-full bg-ink-50 hover:bg-air text-[11.5px]
                               text-ink-600 hover:text-az-700"
                  >
                    {(d.filename as string).replace(/^\d+_/, '').replace(/\.\w+$/, '')}
                  </button>
                ))}
              </div>
            </details>
          )}

          {/* what they are about to send, so nothing is filed unseen */}
          {chosen && (
            <div className="mt-6 pt-4 border-t border-ink-100 text-[12.5px] text-ink-600
                            space-y-1">
              <div>
                {t('pol.vehicle')}: {((chosen.vehicle ?? {}) as Json).make as string}{' '}
                {((chosen.vehicle ?? {}) as Json).model as string} ·{' '}
                {((chosen.vehicle ?? {}) as Json).plate as string}
              </div>
              {route === 'form' && <div>{label(kind)} · {date(when)} · {city || region}</div>}
              {route === 'guided' && (
                <div>{turns.length} {lang === 'de' ? 'Antworten' : 'answers'}</div>
              )}
              <div>
                {files.length} {lang === 'de' ? 'Dateien' : 'files'}
              </div>
            </div>
          )}

          <div className="mt-6 flex items-center gap-2.5">
            <Button onClick={() => void submit()} disabled={submitting || !policy}>
              {submitting ? t('file.submitting') : t('file.submit')}
            </Button>
            <button type="button" onClick={() => setStep('story')}
                    className="text-[12.5px] text-ink-500 hover:text-ink-800">
              ← {t('file.back')}
            </button>
          </div>
        </Card>
      )}
    </div>
  )
}
