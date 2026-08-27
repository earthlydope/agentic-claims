import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Prose } from './Prose'
import { Avatar3D } from './Avatar3D'
import { useT } from '../lib/i18n'
import type { CoworkerReply, Persona } from '../types'

interface Turn {
  id: string
  role: 'you' | 'coworker'
  text: string
  blocked?: boolean
  references?: string[]
  needsPerson?: boolean
  tools?: string[]
}

/**
 * The assistant, docked bottom-right, on every screen and for every role.
 *
 * It is a panel rather than a page because the question you want to ask is almost always
 * about what is currently on the screen — sending someone to a separate view to ask it
 * loses the thing they were looking at. It carries the role's own scope: the same question
 * asked by a handler and by a policyholder reaches different tools, and the panel does not
 * pretend otherwise.
 */
export function CoworkerDock({ persona }: { persona: Persona }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conversation, setConversation] = useState<string | null>(null)
  const feed = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)

  // A role switch is a new person at the desk. Nothing carries over.
  useEffect(() => {
    setTurns([])
    setConversation(null)
    setError(null)
  }, [persona.key])

  useEffect(() => {
    if (feed.current) feed.current.scrollTop = feed.current.scrollHeight
  }, [turns, busy, open])

  useEffect(() => {
    if (open) input.current?.focus()
  }, [open])

  const send = useCallback(
    async (text: string) => {
      const asked = text.trim()
      if (!asked || busy) return
      setQuestion('')
      setError(null)
      setTurns((prev) => [...prev, { id: `q-${Date.now()}`, role: 'you', text: asked }])
      setBusy(true)
      try {
        const reply = (await api.coworkerAsk(
          persona.key, asked, conversation,
        )) as CoworkerReply
        setConversation(reply.conversation_id)
        setTurns((prev) => [
          ...prev,
          {
            id: reply.turn_id,
            role: 'coworker',
            text: reply.answer,
            blocked: reply.blocked,
            references: reply.references,
            needsPerson: reply.needs_a_person,
            tools: reply.tools_used,
          },
        ])
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setBusy(false)
      }
    },
    [busy, conversation, persona.key],
  )

  const starters = (persona.coworker?.starters ?? []).slice(0, 4)

  return (
    <>
      {/* ── the closed pill ─────────────────────────────────────── */}
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2.5 pl-2 pr-5 py-2
                     bg-white rounded-full elev-3 hover:elev-4 transition-all
                     hover:-translate-y-0.5 group"
        >
          <span
            className="relative inline-flex items-center justify-center w-9 h-9 rounded-full"
            style={{ background: 'linear-gradient(145deg,#eef2ff,#e0e7ff)' }}
          >
            <Avatar3D avatar={persona.avatar} accent={persona.accent} size={26} />
            <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full
                             bg-ok-600 ring-2 ring-white" />
          </span>
          <span className="text-left">
            <span className="block text-[13px] text-ink-900 leading-tight">
              {persona.coworker?.name ?? t('cw.open')}
            </span>
            <span className="block text-[11px] text-ink-500 leading-tight">
              {t('cw.open')}
            </span>
          </span>
        </button>
      )}

      {/* ── the open panel ──────────────────────────────────────── */}
      {open && (
        <div
          className="fixed bottom-6 right-6 z-40 w-[min(420px,calc(100vw-3rem))]
                     h-[min(620px,calc(100vh-6rem))] bg-white rounded-3xl elev-4
                     flex flex-col overflow-hidden fade-up"
          role="dialog"
          aria-label={persona.coworker?.name ?? t('cw.open')}
        >
          {/* header */}
          <div className="px-4 py-3 flex items-center gap-3 border-b border-ink-100">
            <Avatar3D avatar={persona.avatar} accent={persona.accent} size={34} />
            <div className="min-w-0 flex-1">
              <div className="text-[13.5px] text-ink-900 leading-tight truncate">
                {persona.coworker?.name}
              </div>
              <div className="text-[11.5px] text-ink-500 leading-tight truncate">
                {persona.coworker?.tagline}
              </div>
            </div>
            {turns.length > 0 && (
              <button
                type="button"
                title={t('cw.clear')}
                onClick={() => { setTurns([]); setConversation(null) }}
                className="p-1.5 rounded-full text-ink-400 hover:text-ink-700 hover:bg-ink-50"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
                     strokeLinecap="round" className="w-4 h-4">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
            )}
            <button
              type="button"
              title={t('cw.close')}
              onClick={() => setOpen(false)}
              className="p-1.5 rounded-full text-ink-400 hover:text-ink-700 hover:bg-ink-50"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                   strokeLinecap="round" className="w-4 h-4">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>

          {/* feed */}
          <div ref={feed} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {turns.length === 0 && (
              <div className="space-y-3">
                <p className="text-[12.5px] text-ink-500 leading-relaxed">
                  {persona.coworker?.tagline}
                </p>
                <div className="text-[11px] text-ink-400 uppercase tracking-wide pt-1">
                  {t('cw.tryAsking')}
                </div>
                <div className="space-y-1.5">
                  {starters.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => send(s)}
                      className="w-full text-left px-3.5 py-2.5 rounded-2xl bg-ink-50
                                 hover:bg-air text-[12.5px] text-ink-700 hover:text-az-700
                                 transition-colors leading-snug"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {turns.map((turn) =>
              turn.role === 'you' ? (
                <div key={turn.id} className="flex justify-end">
                  <div className="max-w-[85%] px-3.5 py-2.5 rounded-2xl rounded-br-md
                                  bg-az-600 text-white text-[12.5px] leading-relaxed">
                    {turn.text}
                  </div>
                </div>
              ) : (
                <div key={turn.id} className="flex gap-2.5">
                  <Avatar3D avatar={persona.avatar} accent={persona.accent} size={26}
                            className="mt-0.5" />
                  <div className="min-w-0 flex-1 space-y-2">
                    <div
                      className={`px-3.5 py-2.5 rounded-2xl rounded-tl-md text-[12.5px]
                                  leading-relaxed ${
                        turn.blocked
                          ? 'bg-warn-100 text-warn-700'
                          : 'bg-ink-50 text-ink-800'
                      }`}
                    >
                      {turn.blocked && (
                        <div className="text-[11px] uppercase tracking-wide mb-1 opacity-70">
                          {t('cw.blocked')}
                        </div>
                      )}
                      <Prose text={turn.text} />
                    </div>

                    {turn.needsPerson && (
                      <div className="flex items-center gap-1.5 text-[11.5px] text-warn-700">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                             strokeWidth="1.8" className="w-3.5 h-3.5" strokeLinecap="round">
                          <path d="M12 9v4m0 3h.01M10.3 4.3 2.6 18a1.8 1.8 0 0 0 1.6 2.7h15.6a1.8 1.8 0 0 0 1.6-2.7L13.7 4.3a1.9 1.9 0 0 0-3.4 0z" />
                        </svg>
                        {t('cw.needsPerson')}
                      </div>
                    )}

                    {!!turn.references?.length && (
                      <div className="text-[11px] text-ink-500 leading-relaxed">
                        <span className="text-ink-400">{t('cw.basedOn')}: </span>
                        {turn.references.join(' · ')}
                      </div>
                    )}
                  </div>
                </div>
              ),
            )}

            {busy && (
              <div className="flex gap-2.5 items-center">
                <Avatar3D avatar={persona.avatar} accent={persona.accent} size={26} />
                <div className="px-3.5 py-2.5 rounded-2xl rounded-tl-md bg-ink-50">
                  <span className="flex gap-1">
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        className="w-1.5 h-1.5 rounded-full bg-ink-400 animate-bounce"
                        style={{ animationDelay: `${i * 0.14}s` }}
                      />
                    ))}
                  </span>
                </div>
              </div>
            )}

            {error && (
              <div className="text-[11.5px] text-stop-700 bg-stop-100 rounded-xl px-3 py-2">
                {error}
              </div>
            )}
          </div>

          {/* composer */}
          <div className="px-3 pb-3 pt-2 border-t border-ink-100">
            {turns.length > 0 && starters.length > 0 && (
              <div className="flex gap-1.5 overflow-x-auto pb-2 -mx-1 px-1
                              [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {starters.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => send(s)}
                    className="shrink-0 px-3 py-1.5 rounded-full bg-ink-50 hover:bg-air
                               text-[11.5px] text-ink-600 hover:text-az-700 whitespace-nowrap"
                  >
                    {s.length > 34 ? `${s.slice(0, 33)}…` : s}
                  </button>
                ))}
              </div>
            )}
            <div className="flex items-end gap-2 bg-ink-50 rounded-2xl px-3 py-2">
              <textarea
                ref={input}
                rows={1}
                value={question}
                onChange={(e) => {
                  setQuestion(e.target.value)
                  e.target.style.height = 'auto'
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 110)}px`
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    send(question)
                  }
                }}
                placeholder={t('cw.placeholder')}
                className="flex-1 bg-transparent resize-none text-[13px] text-ink-900
                           placeholder:text-ink-400 outline-none leading-relaxed py-1"
              />
              <button
                type="button"
                onClick={() => send(question)}
                disabled={busy || !question.trim()}
                className="shrink-0 w-8 h-8 rounded-full bg-az-600 text-white flex items-center
                           justify-center disabled:opacity-30 disabled:cursor-not-allowed
                           hover:bg-az-700 transition-colors"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                     strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
                  <path d="M5 12h13M12 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
