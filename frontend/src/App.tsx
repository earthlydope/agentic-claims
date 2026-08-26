import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { Shell } from './components/Shell'
import { ErrorNote, Spinner } from './components/ui'
import { Overview } from './views/Overview'
import { FileClaim } from './views/FileClaim'
import { Claims } from './views/Claims'
import { ClaimWorkbench } from './views/ClaimWorkbench'
import { ReviewConsole } from './views/ReviewConsole'
import { ZeroTrust } from './views/ZeroTrust'
import { AgentsData } from './views/AgentsData'
import { Observability } from './views/Observability'

function useHashRoute() {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || 'overview')
  useEffect(() => {
    const onChange = () => setRoute(window.location.hash.slice(1) || 'overview')
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  const navigate = useCallback((next: string) => {
    window.location.hash = next
  }, [])
  return { route, navigate }
}

export default function App() {
  const { route, navigate } = useHashRoute()
  const [health, setHealth] = useState<{
    tenant: string
    model_mode: string
    default_run_mode?: string
    hybrid_live_agents?: number
    agent_count?: number
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(h as NonNullable<typeof health>))
      .catch((e: Error) =>
        setError(
          `Could not reach the platform API. Is the backend running on port 8099? (${e.message})`,
        ),
      )
  }, [])

  const onReset = async () => {
    setResetting(true)
    try {
      await api.reset()
      setRefreshKey((k) => k + 1)
      navigate('overview')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setResetting(false)
    }
  }

  if (error && !health) {
    return (
      <div className="p-10 max-w-2xl">
        <ErrorNote message={error} />
        <pre className="mt-4 font-mono text-[11.5px] bg-white border border-ink-200 rounded p-4 text-ink-700">
{`cd agentic-claims/backend
.venv/bin/python -m uvicorn app.main:app --port 8099`}
        </pre>
      </div>
    )
  }

  if (!health) return <Spinner label="Connecting to the claims platform…" />

  const [section, param] = route.split('/')

  const view = () => {
    switch (section) {
      case 'file':
        return <FileClaim onOpenClaim={(ref) => navigate(`claims/${ref}`)} />
      case 'claims':
        return param ? (
          // Keyed on the reference so switching claims mounts a fresh workbench —
          // a run trace must never bleed from one claim into another.
          <ClaimWorkbench key={param} reference={param} onBack={() => navigate('claims')} />
        ) : (
          <Claims onOpen={(ref) => navigate(`claims/${ref}`)} refreshKey={refreshKey} />
        )
      case 'review':
        return <ReviewConsole onOpenClaim={(ref) => navigate(`claims/${ref}`)} />
      case 'zerotrust':
        return <ZeroTrust />
      case 'agents':
        return <AgentsData />
      case 'observability':
        return <Observability />
      default:
        return (
          <Overview
            onNavigate={navigate}
            onOpenClaim={(ref) => navigate(`claims/${ref}`)}
            refreshKey={refreshKey}
          />
        )
    }
  }

  return (
    <Shell
      route={route}
      onNavigate={navigate}
      modelMode={health.model_mode}
      defaultRunMode={health.default_run_mode}
      hybridAgents={health.hybrid_live_agents}
      agentCount={health.agent_count}
      tenant="Allianz Austria"
      onReset={onReset}
      resetting={resetting}
    >
      {view()}
    </Shell>
  )
}
