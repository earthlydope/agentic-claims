import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { Shell } from './components/Shell'
import { Button, ErrorNote, Spinner } from './components/ui'
import { Coworker } from './views/Coworker'
import { MyClaims } from './views/MyClaims'
import { ModelUsage } from './views/ModelUsage'
import { WorkQueue } from './views/WorkQueue'
import { FileClaim } from './views/FileClaim'
import { ClaimWorkbench } from './views/ClaimWorkbench'
import { ZeroTrust } from './views/ZeroTrust'
import { AgentsData } from './views/AgentsData'
import { Observability } from './views/Observability'
import { TeamView } from './views/TeamView'
import type { Json, Persona } from './types'

/** Hash routes read `#persona/feature[/param]`, so a view is always shareable. */
function useRoute() {
  const [hash, setHash] = useState(() => window.location.hash.slice(1))
  useEffect(() => {
    const onChange = () => setHash(window.location.hash.slice(1))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  const [persona = '', feature = '', param = ''] = hash.split('/')
  const go = useCallback((next: string) => {
    window.location.hash = next
  }, [])
  return { persona, feature, param, go }
}

export default function App() {
  const { persona: routePersona, feature: routeFeature, param, go } = useRoute()
  const [personas, setPersonas] = useState<Persona[] | null>(null)
  const [platform, setPlatform] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [defaultPersona, setDefaultPersona] = useState('claims_handler')

  useEffect(() => {
    Promise.all([api.personas(), api.platform()])
      .then(([p, plat]) => {
        setPersonas((p as { personas: Persona[] }).personas)
        setDefaultPersona((p as { default: string }).default)
        setPlatform(plat)
      })
      .catch((e: Error) =>
        setError(
          `Could not reach the platform API on port 8099. ${e.message}`,
        ),
      )
  }, [])

  const active = useMemo(() => {
    if (!personas) return null
    return (
      personas.find((p) => p.key === routePersona) ??
      personas.find((p) => p.key === defaultPersona) ??
      personas[0]
    )
  }, [personas, routePersona, defaultPersona])

  const feature = useMemo(() => {
    if (!active) return ''
    const keys = active.features.map((f) => f.key)
    return keys.includes(routeFeature) ? routeFeature : keys[0]
  }, [active, routeFeature])

  // Keep the URL honest: a persona switch lands on a view that persona actually has.
  useEffect(() => {
    if (!active) return
    if (routePersona !== active.key || routeFeature !== feature) {
      go(`${active.key}/${feature}${param ? `/${param}` : ''}`)
    }
  }, [active, feature, routePersona, routeFeature, param, go])

  const onReset = async () => {
    setResetting(true)
    try {
      await api.reset()
      setRefreshKey((k) => k + 1)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setResetting(false)
    }
  }

  if (error && !personas) {
    return (
      <div className="p-12 max-w-2xl">
        <ErrorNote message={error} />
        <pre className="mt-5 font-mono text-[12px] bg-ink-50 rounded-xl p-5 text-ink-700">
{`cd agentic-claims && ./start.sh`}
        </pre>
      </div>
    )
  }

  if (!personas || !active) return <Spinner label="Connecting to the claims platform…" />

  const openClaim = (ref: string) => go(`${active.key}/${feature}/${ref}`)

  const view = () => {
    // A claim reference in the URL opens the workbench, whichever view you came from.
    if (param.startsWith('AT-')) {
      return (
        <ClaimWorkbench
          key={param}
          reference={param}
          persona={active}
          onBack={() => go(`${active.key}/${feature}`)}
        />
      )
    }

    switch (feature) {
      case 'my_claims':
        return (
          <MyClaims
            persona={active}
            onFile={() => go(`${active.key}/file_claim`)}
            onOpenClaim={openClaim}
            refreshKey={refreshKey}
          />
        )
      case 'file_claim':
        return <FileClaim onOpenClaim={openClaim} />
      case 'work_queue':
      case 'assessment_queue':
      case 'approvals':
      case 'investigations':
      case 'recovery':
        return (
          <WorkQueue
            persona={active}
            feature={feature}
            onOpenClaim={openClaim}
            refreshKey={refreshKey}
          />
        )
      case 'team':
        return <TeamView persona={active} refreshKey={refreshKey} />
      case 'governance':
        return <ZeroTrust />
      case 'evaluations':
        return <Observability />
      case 'llm_usage':
        return <ModelUsage />
      case 'platform':
        return <AgentsData />
      case 'coworker':
        return <Coworker persona={active} />
      default:
        return (
          <div className="py-16 text-center">
            <p className="text-[14px] text-ink-600">
              Nothing is wired to “{feature}” yet.
            </p>
            <div className="mt-4">
              <Button variant="secondary" onClick={() => go(`${active.key}/coworker`)}>
                Ask your coworker instead
              </Button>
            </div>
          </div>
        )
    }
  }

  return (
    <Shell
      personas={personas}
      active={active}
      onSwitch={(key) => go(key)}
      feature={feature}
      onFeature={(f) => go(`${active.key}/${f}`)}
      platform={platform}
      onReset={onReset}
      resetting={resetting}
    >
      {view()}
    </Shell>
  )
}
