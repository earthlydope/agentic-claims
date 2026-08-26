import type { Json, TraceEvent } from './types'

const BASE = '/api'

async function req<T = Json>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status} ${detail}`)
  }
  return res.json() as Promise<T>
}

const get = <T = Json>(p: string) => req<T>(p)
const post = <T = Json>(p: string, body?: unknown) =>
  req<T>(p, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  health: () => get('/health'),
  platform: () => get('/platform'),
  agents: () => get('/agents'),
  agent: (key: string) => get(`/agents/${key}`),
  personas: () => get('/personas'),
  semantic: () => get('/semantic'),
  clauses: () => get('/semantic/clauses'),
  semanticSearch: (question: string, product?: string | null, language = 'en') =>
    post('/semantic/search', { question, product: product ?? null, language }),
  semanticQuery: (query_name: string, args: Json = {}) =>
    post('/semantic/query', { query_name, args }),
  preflightLink: (url: string) => post('/preflight/link', { url }),
  reset: () => post('/admin/reset'),

  claims: (liveOnly = false) =>
    get(`/claims${liveOnly ? '?live_only=true' : ''}`),
  claim: (ref: string) => get(`/claims/${ref}`),
  intake: (body: Json) => post('/claims/intake', body),
  runClaim: (ref: string, userId = 'system', mode?: string) =>
    post(
      `/claims/${ref}/run?user_id=${encodeURIComponent(userId)}` +
        (mode ? `&mode=${encodeURIComponent(mode)}` : ''),
    ),

  reviewQueue: (queue?: string) =>
    get(`/review/queue${queue ? `?queue=${encodeURIComponent(queue)}` : ''}`),
  reviewStaff: () => get('/review/staff'),
  reviewTask: (id: string) => get(`/review/tasks/${id}`),
  assignTask: (id: string, user_id: string) =>
    post(`/review/tasks/${id}/assign`, { user_id }),
  decideTask: (id: string, body: Json) => post(`/review/tasks/${id}/decide`, body),

  posture: () => get('/security/posture'),
  ledger: () => get('/security/ledger'),
  verify: () => post('/security/verify'),
  securityEvents: () => get('/security/events'),
  regression: () => post('/security/regression'),
  attackReplay: () => post('/security/attack-replay'),
  attackLibrary: () => get('/security/attack-library'),
  screen: (text: string, surface = 'user_message') =>
    post('/security/screen', { text, surface }),
  guard: (pkg: Json) => post('/security/guard', { package: pkg }),
  sandbox: (code: string) => post('/security/sandbox', { code }),
  sandboxCorpus: () => get('/security/sandbox-corpus'),
  outboundGuard: (body: string, approved_amount_eur: number | null) =>
    post('/security/outbound-guard', { body, approved_amount_eur }),
  tamperDrill: (reference: string, new_amount_eur: number) =>
    post('/security/drills/tamper', { reference, new_amount_eur }),
  restoreDrill: (reference: string) =>
    post('/security/drills/restore', { reference }),

  metrics: () => get('/metrics'),
  observability: (limit = 25) => get(`/observability?limit=${limit}`),
  run: (id: string) => get(`/runs/${id}`),
  evalCases: () => get('/evals/cases'),
  runEvals: (mode?: string) =>
    post(`/evals/run${mode ? `?mode=${encodeURIComponent(mode)}` : ''}`),
}

/** Stream a claim run over SSE. Returns an abort handle. */
export function streamRun(
  reference: string,
  onEvent: (ev: TraceEvent) => void,
  onDone: () => void,
  onError: (message: string) => void,
  userId = 'system',
  mode?: string,
): () => void {
  const source = new EventSource(
    `${BASE}/claims/${reference}/stream?user_id=${encodeURIComponent(userId)}` +
      (mode ? `&mode=${encodeURIComponent(mode)}` : ''),
  )
  let finished = false

  const handle = (raw: MessageEvent) => {
    try {
      const parsed = JSON.parse(raw.data) as TraceEvent & { detail?: string }
      if (parsed.kind === 'error') {
        onError(parsed.detail ?? 'The run failed.')
        finished = true
        source.close()
        onDone()
        return
      }
      onEvent(parsed)
      if (parsed.kind === 'run_end') {
        finished = true
        source.close()
        onDone()
      }
    } catch {
      /* ignore malformed frames */
    }
  }

  // The server names each frame after the event kind, so listen broadly.
  for (const kind of [
    'message', 'run_start', 'guard', 'preflight', 'step_start', 'tool_call',
    'tool_result', 'agent_output', 'security', 'step_end', 'sign', 'write',
    'run_end', 'error',
  ]) {
    source.addEventListener(kind, handle as EventListener)
  }

  source.onerror = () => {
    if (!finished) {
      source.close()
      onError('The connection to the run stream dropped.')
      onDone()
    }
  }

  return () => {
    finished = true
    source.close()
  }
}
