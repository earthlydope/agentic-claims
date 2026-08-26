import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Prose } from '../components/Prose'
import {
  Avatar, Button, Card, Chip, ErrorNote, Mono, Notice, PageHeader, Spinner,
  TextInput,
} from '../components/ui'
import { ms } from '../lib/format'
import type { CoworkerReply, Json, Persona } from '../types'

interface Turn {
  id: string
  role: 'you' | 'coworker'
  text: string
  blocked?: boolean
  firewall?: Json
  references?: string[]
  actions?: string[]
  tools?: string[]
  needsPerson?: boolean
  model?: string
  runtime?: string
  latency?: number
  outboundGuard?: Json | null
}

export function Coworker({ persona }: { persona: Persona }) {
  const [profile, setProfile] = useState<Json | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conversation, setConversation] = useState<string | null>(null)
  const feed = useRef<HTMLDivElement>(null)

  const load = useCallback(() => {
    api
      .coworkerProfile(persona.key)
      .then(setProfile)
      .catch((e: Error) => setError(e.message))
  }, [persona.key])

  useEffect(() => {
    setTurns([])
    setConversation(null)
    setProfile(null)
    load()
  }, [load])

  useEffect(() => {
    if (feed.current) feed.current.scrollTop = feed.current.scrollHeight
  }, [turns, busy])

  const send = async (text: string) => {
    const asked = text.trim()
    if (!asked || busy) return
    setQuestion('')
    setError(null)
    setTurns((t) => [...t, { id: `q-${Date.now()}`, role: 'you', text: asked }])
    setBusy(true)
    try {
      const reply = (await api.coworkerAsk(persona.key, asked, conversation)) as CoworkerReply
      setConversation(reply.conversation_id)
      setTurns((t) => [
        ...t,
        {
          id: reply.turn_id,
          role: 'coworker',
          text: reply.answer,
          blocked: reply.blocked,
          firewall: reply.firewall,
          references: reply.references,
          actions: reply.suggested_actions,
          tools: reply.tools_used,
          needsPerson: reply.needs_a_person,
          model: reply.model,
          runtime: reply.runtime,
          latency: reply.latency_ms,
          outboundGuard: reply.outbound_guard,
        },
      ])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (error && !profile) return <ErrorNote message={error} />
  if (!profile) return <Spinner />

  const cw = profile.coworker as Json
  const tools = (cw.tools as Json[]) ?? []
  const starters = (cw.starters as string[]) ?? []
  const cannot = (cw.cannot as string[]) ?? []

  return (
    <>
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-2">
            <Avatar initials={persona.initials} accent={persona.accent} size={20} />
            {persona.name} · {persona.role_label}
          </span>
        }
        title={cw.name as string}
        lede={cw.remit as string}
        right={
          turns.length > 0 ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setTurns([])
                setConversation(null)
              }}
            >
              New conversation
            </Button>
          ) : undefined
        }
      />

      <div className="grid grid-cols-[1fr_minmax(300px,340px)] gap-5 items-start">
        {/* ── Conversation ─────────────────────────────────────── */}
        <Card pad={false} className="flex flex-col min-h-[600px]">
          <div ref={feed} className="flex-1 overflow-y-auto px-6 py-6 max-h-[620px]">
            {turns.length === 0 ? (
              <div className="max-w-xl mx-auto text-center py-10">
                <div
                  className={`w-14 h-14 rounded-2xl mx-auto grid place-items-center ${
                    persona.accent === 'teal'
                      ? 'bg-teal-100 text-teal-600'
                      : persona.accent === 'amber'
                        ? 'bg-amber-100 text-amber-600'
                        : persona.accent === 'indigo'
                          ? 'bg-indigo-100 text-indigo-600'
                          : persona.accent === 'rose'
                            ? 'bg-rose-100 text-rose-600'
                            : persona.accent === 'slate'
                              ? 'bg-slate-100 text-slate-600'
                              : 'bg-air text-az-700'
                  }`}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                       className="w-7 h-7">
                    <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
                  </svg>
                </div>
                <h3 className="text-[18px] text-ink-900 mt-4">{cw.name as string}</h3>
                <p className="text-[13px] text-ink-600 mt-1.5">{cw.tagline as string}</p>
                <div className="mt-7 space-y-2">
                  {starters.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => send(s)}
                      className="w-full text-left px-4 py-3 rounded-xl bg-ink-50 hover:bg-air text-[13px] text-ink-800 hover:text-az-700 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-6 max-w-3xl">
                {turns.map((t) =>
                  t.role === 'you' ? (
                    <div key={t.id} className="flex justify-end fade-up">
                      <div className="bg-air text-info-700 rounded-2xl rounded-br-md px-4 py-2.5 text-[13.5px] max-w-[80%] leading-relaxed">
                        {t.text}
                      </div>
                    </div>
                  ) : (
                    <div key={t.id} className="flex gap-3 fade-up">
                      <Avatar initials="AI" accent={persona.accent} size={30} />
                      <div className="min-w-0 flex-1">
                        {t.blocked ? (
                          <Notice tone="stop" title="Stopped at the gateway">
                            {t.text}
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {(
                                ((t.firewall as Json)?.violations as Json[]) ?? []
                              ).map((v, i) => (
                                <Chip key={i} tone="stop" mono>
                                  {v.rule_id as string}
                                </Chip>
                              ))}
                            </div>
                            <p className="mt-2">
                              A coworker's input is screened exactly like a customer's. It
                              is another agent identity, not an exception.
                            </p>
                          </Notice>
                        ) : (
                          <>
                            <Prose
                              text={t.text}
                              className="text-[13.5px] text-ink-800"
                            />

                            {(t.actions?.length ?? 0) > 0 && (
                              <div className="mt-3">
                                <div className="text-[11.5px] text-ink-500 mb-1.5">
                                  Suggested — yours to do, not its
                                </div>
                                <ul className="space-y-1">
                                  {t.actions!.map((a, i) => (
                                    <li
                                      key={i}
                                      className="text-[12.5px] text-az-700 flex gap-2"
                                    >
                                      <span className="text-ink-400">→</span>
                                      {a}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {t.needsPerson && (
                              <div className="mt-3">
                                <Notice tone="warn">
                                  It flagged this as one a person should answer.
                                </Notice>
                              </div>
                            )}

                            <div className="flex items-center gap-2 mt-3 flex-wrap">
                              {(t.references ?? []).slice(0, 6).map((r) => (
                                <Chip key={r} tone="blue" mono>
                                  {r}
                                </Chip>
                              ))}
                              {(t.tools ?? []).map((tool) => (
                                <Chip key={tool} tone="ghost" mono>
                                  {tool}
                                </Chip>
                              ))}
                              {t.outboundGuard ? (
                                <Chip
                                  tone={
                                    (t.outboundGuard as Json).passed ? 'ok' : 'stop'
                                  }
                                >
                                  outbound guard{' '}
                                  {(t.outboundGuard as Json).passed ? 'passed' : 'withheld'}
                                </Chip>
                              ) : null}
                            </div>
                            <div className="text-[11px] text-ink-400 mt-2">
                              {t.runtime} · {t.model} · {ms(t.latency)}
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  ),
                )}

                {busy && (
                  <div className="flex gap-3">
                    <Avatar initials="AI" accent={persona.accent} size={30} />
                    <div className="flex items-center gap-1.5 pt-2.5">
                      {[0, 1, 2].map((i) => (
                        <span
                          key={i}
                          className="typing-dot w-1.5 h-1.5 rounded-full bg-ink-400"
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="px-6 py-4 border-t border-ink-100">
            {error && (
              <div className="mb-3">
                <ErrorNote message={error} />
              </div>
            )}
            <div className="flex gap-2 items-center">
              <TextInput
                value={question}
                onChange={setQuestion}
                placeholder={`Ask ${cw.name as string}…`}
                onEnter={() => send(question)}
              />
              <Button onClick={() => send(question)} busy={busy} disabled={!question.trim()}>
                Send
              </Button>
            </div>
            <p className="text-[11px] text-ink-400 mt-2.5">
              It reads, explains and drafts. Approving, sending and settling stay with you.
            </p>
          </div>
        </Card>

        {/* ── What it can and cannot do ─────────────────────────── */}
        <div className="space-y-4 sticky top-[92px]">
          <Card title="What it can reach" subtitle={`${tools.length} scoped tools`} dense>
            <div className="space-y-3">
              {tools.map((t) => (
                <div key={t.name as string}>
                  <div className="flex items-center gap-2">
                    <span className="text-[12.5px] text-ink-900">{t.label as string}</span>
                    <Chip tone="ghost" mono>
                      {t.risk_class as string}
                    </Chip>
                  </div>
                  <p className="text-[11.5px] text-ink-600 leading-relaxed mt-0.5">
                    {t.description as string}
                  </p>
                </div>
              ))}
            </div>
          </Card>

          <Card title="What it will not do" dense>
            <ul className="space-y-1.5">
              {cannot.map((c) => (
                <li key={c} className="text-[12.5px] text-ink-700 flex gap-2">
                  <span className="text-stop-600 shrink-0">×</span>
                  {c}
                </li>
              ))}
            </ul>
            <p className="text-[11.5px] text-ink-500 mt-3 leading-relaxed">
              A coworker is another agent identity. It goes through the same inbound
              firewall, reaches only its persona's tools, and anything it says to a
              customer goes through the same outbound guard.
            </p>
          </Card>

          {((profile.history as Json[]) ?? []).length > 0 && (
            <Card title="Earlier" dense>
              <div className="space-y-2.5 max-h-[280px] overflow-y-auto">
                {((profile.history as Json[]) ?? [])
                  .slice(-8)
                  .reverse()
                  .map((h) => (
                    <button
                      key={h.turn_id as string}
                      type="button"
                      onClick={() => send(h.question as string)}
                      className="w-full text-left group"
                    >
                      <div className="text-[12px] text-ink-700 group-hover:text-az-700 truncate">
                        {h.question as string}
                      </div>
                      <div className="text-[11px] text-ink-400 flex items-center gap-1.5">
                        {h.blocked ? (
                          <Chip tone="stop">blocked</Chip>
                        ) : (
                          <Mono className="text-ink-400">
                            {((h.tools_used as string[]) ?? []).join(' ') || '—'}
                          </Mono>
                        )}
                      </div>
                    </button>
                  ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
