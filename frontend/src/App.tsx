import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { Shell } from './components/Shell'
import { CoworkerDock } from './components/CoworkerDock'
import { Button, ErrorNote, Spinner } from './components/ui'
import { LanguageProvider, useT } from './lib/i18n'
import { MyClaims } from './views/MyClaims'
import { MyClaimDetail } from './views/MyClaimDetail'
import { MyPolicies } from './views/MyPolicies'
import { ModelUsage } from './views/ModelUsage'
import { WorkQueue } from './views/WorkQueue'
import { FileClaim } from './views/FileClaim'
import { ClaimWorkbench } from './views/ClaimWorkbench'
import { ZeroTrust } from './views/ZeroTrust'
import { TeamView } from './views/TeamView'
import type { Persona } from './types'

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

function Platform() {
  const t = useT()
  const { persona: routePersona, feature: routeFeature, param, go } = useRoute()
  const [personas, setPersonas] = useState<Persona[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [defaultPersona, setDefaultPersona] = useState('claim_handler')

  useEffect(() => {
    api
      .personas()
      .then((p) => {
        setPersonas((p as { personas: Persona[] }).personas)
        setDefaultPersona((p as { default: string }).default)
      })
      .catch((e: Error) => setError(`Could not reach the platform API. ${e.message}`))
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

  // Keep the URL honest: a role switch lands on a view that role actually has.
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

  if (!personas || !active) return <Spinner label={t('g.loading')} />

  const openClaim = (ref: string) => go(`${active.key}/${feature}/${ref}`)

  const view = () => {
    // A claim reference in the URL opens the file, whichever view you came from.
    if (param.startsWith('AT-2')) {
      // A customer opening their own claim gets a customer's view of it. The workbench
      // carries the run trace, the firewall verdict, the policy checks and the risk
      // picture — everything the outbound guard exists to keep away from a claimant.
      if (active.kind === 'customer') {
        return (
          <MyClaimDetail
            key={param}
            reference={param}
            persona={active}
            onBack={() => go(`${active.key}/${feature}`)}
          />
        )
      }
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
      case 'my_policies':
        return (
          <MyPolicies
            persona={active}
            onClaimOn={(policyNumber) => go(`${active.key}/file_claim/${policyNumber}`)}
            onOpenClaim={openClaim}
            refreshKey={refreshKey}
          />
        )
      case 'file_claim':
        return (
          <FileClaim
            persona={active}
            presetPolicy={param.startsWith('AT-MOT-') ? param : undefined}
            onOpenClaim={openClaim}
          />
        )
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
      case 'operations':
        return <TeamView persona={active} refreshKey={refreshKey} />
      case 'governance':
        return <ZeroTrust />
      case 'model_usage':
        return <ModelUsage />
      default:
        return (
          <div className="py-16 text-center">
            <p className="text-[14px] text-ink-600">Nothing is wired to “{feature}” yet.</p>
            <div className="mt-4">
              <Button
                variant="secondary"
                onClick={() => go(`${active.key}/${active.features[0].key}`)}
              >
                {t('cl.back')}
              </Button>
            </div>
          </div>
        )
    }
  }

  return (
    <>
      <Shell
        personas={personas}
        active={active}
        onSwitch={(key) => go(key)}
        feature={feature}
        onFeature={(f) => go(`${active.key}/${f}`)}
        onReset={onReset}
        resetting={resetting}
      >
        {view()}
      </Shell>
      {/* Every role gets one, on every screen. */}
      <CoworkerDock persona={active} />
    </>
  )
}

export default function App() {
  return (
    <LanguageProvider>
      <Platform />
    </LanguageProvider>
  )
}
