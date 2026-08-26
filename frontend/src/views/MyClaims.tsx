import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import {
  Avatar, Button, Card, Chip, Empty, ErrorNote, Field, KeyValueGrid, Notice,
  PageHeader, Spinner, toneOf,
} from '../components/ui'
import { ago, eur } from '../lib/format'
import type { Json, Persona } from '../types'

export function MyClaims({
  persona, onFile, onOpenClaim, refreshKey,
}: {
  persona: Persona
  onFile: () => void
  onOpenClaim: (ref: string) => void
  refreshKey: number
}) {
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
  if (!data) return <Spinner />

  const claims = (data.claims as Json[]) ?? []

  return (
    <>
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-2">
            <Avatar initials={persona.initials} accent={persona.accent} size={20} />
            {persona.name} · {persona.location}
          </span>
        }
        title="My claims"
        lede="Where each of your claims stands, in plain language, without having to ring anyone."
        right={<Button onClick={onFile}>Report an accident</Button>}
      />

      {claims.length === 0 ? (
        <Card>
          <Empty action={<Button onClick={onFile}>Report an accident</Button>}>
            You have no claims on record.
          </Empty>
        </Card>
      ) : (
        <div className="space-y-4">
          {claims.map((c) => {
            const status = (c.status as Json) ?? {}
            return (
              <Card key={c.reference as string}>
                <div className="flex items-start justify-between gap-6">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <span className="font-mono text-[14px] text-ink-900">
                        {c.reference as string}
                      </span>
                      <Chip tone={toneOf(status.tone as string)}>
                        {status.label as string}
                      </Chip>
                      {c.with_a_person ? <Chip tone="blue">with a person</Chip> : null}
                    </div>
                    <p className="text-[13.5px] text-ink-700 mt-2 leading-relaxed max-w-2xl">
                      {status.description as string}
                    </p>

                    <div className="mt-4">
                      <KeyValueGrid cols={4}>
                        <Field label="What happened">
                          {String(c.incident_type ?? '').replace(/_/g, ' ')}
                        </Field>
                        <Field label="Date of accident">
                          {(c.incident_date as string) ?? '—'}
                        </Field>
                        <Field label="Reported">{ago(c.reported_at as string)}</Field>
                        <Field label="Settlement">
                          {(c.settlement_amount_eur as number) > 0
                            ? eur(c.settlement_amount_eur as number)
                            : c.estimate_eur
                              ? `${eur(c.estimate_eur as number)} estimated`
                              : 'not yet decided'}
                        </Field>
                      </KeyValueGrid>
                    </div>

                    {c.latest_message ? (
                      <div className="mt-4 bg-ink-50 rounded-xl p-4">
                        <div className="text-[12px] text-ink-500 mb-1.5">
                          What we last told you
                        </div>
                        <div className="text-[13.5px] text-ink-900 mb-2">
                          {(c.latest_message as Json).subject as string}
                        </div>
                        {String((c.latest_message as Json).body ?? '')
                          .split('\n\n')
                          .map((para, i) => (
                            <p
                              key={i}
                              className="text-[13px] text-ink-700 leading-relaxed mb-2 last:mb-0"
                            >
                              {para}
                            </p>
                          ))}
                      </div>
                    ) : null}
                  </div>

                  <div className="shrink-0">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => onOpenClaim(c.reference as string)}
                    >
                      See the detail
                    </Button>
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      <div className="mt-5">
        <Notice tone="blue" title="You can always reach a person">
          Nothing here is decided by a machine alone. Any decision that affects what you are
          paid is confirmed by a named person, and you can ask for one at any point.
        </Notice>
      </div>
    </>
  )
}
