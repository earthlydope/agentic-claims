import type { Json, TraceEvent } from './types'

/** Cloud Run origin in production (`VITE_API_BASE`); Vite proxy `/api` locally. */
const ROOT = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')
const BASE = ROOT ? `${ROOT}/api` : '/api'

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
  persona: (key: string) => get(`/personas/${key}`),
  lifecycle: () => get('/lifecycle'),
  work: (persona: string) => get(`/work?persona=${encodeURIComponent(persona)}`),
  coworkerProfile: (persona: string) => get(`/coworker/${encodeURIComponent(persona)}`),
  coworkerAsk: (persona: string, question: string, conversation_id?: string | null) =>
    post('/coworker/ask', { persona, question, conversation_id: conversation_id ?? null }),
  llmUsage: (days = 28) => get(`/llm-usage?days=${days}`),
  semantic: () => get('/semantic'),
  clauses: () => get('/semantic/clauses'),
  semanticSearch: (question: string, product?: string | null, language = 'en') =>
    post('/semantic/search', { question, product: product ?? null, language }),
  semanticQuery: (query_name: string, args: Json = {}) =>
    post('/semantic/query', { query_name, args }),
  preflightLink: (url: string) => post('/preflight/link', { url }),
  reset: () => post('/admin/reset'),
  testDocuments: () => get('/test-documents'),
  /** Fetch one sample document as a File, ready to attach. */
  fetchTestDocument: async (filename: string, mime: string) => {
    const res = await fetch(`${BASE}/test-documents/${encodeURIComponent(filename)}`)
    if (!res.ok) throw new Error(`Could not load ${filename} (${res.status})`)
    return new File([await res.blob()], filename, { type: mime })
  },

  claims: (liveOnly = false) =>
    get(`/claims${liveOnly ? '?live_only=true' : ''}`),
  claim: (ref: string) => get(`/claims/${ref}`),
  intake: (body: Json) => post('/claims/intake', body),
  /** File a claim with real documents attached. */
  intakeUpload: async (form: FormData) => {
    const res = await fetch(`${BASE}/claims/intake/upload`, {
      method: 'POST',
      body: form,
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
    return res.json() as Promise<Json>
  },
  runClaim: (
    ref: string,
    userId = 'system',
    opts: { mode?: string; runtime?: string; persona?: string } = {},
  ) => {
    const q = new URLSearchParams({ user_id: userId })
    if (opts.mode) q.set('mode', opts.mode)
    if (opts.runtime) q.set('runtime', opts.runtime)
    if (opts.persona) q.set('persona', opts.persona)
    return post(`/claims/${ref}/run?${q.toString()}`)
  },

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
  opts: { mode?: string; runtime?: string; persona?: string } = {},
): () => void {
  const q = new URLSearchParams({ user_id: userId })
  if (opts.mode) q.set('mode', opts.mode)
  if (opts.runtime) q.set('runtime', opts.runtime)
  if (opts.persona) q.set('persona', opts.persona)
  const source = new EventSource(`${BASE}/claims/${reference}/stream?${q.toString()}`)
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
