import { useEffect, useState } from 'react'
import { api } from '../api'
import {
  Badge, Button, Card, Empty, ErrorNote, Field, JsonBlock, KeyValueGrid, Mono,
  PageHeader, Spinner, Table, Tabs, Td,
} from '../components/ui'
import { eur, num } from '../lib/format'
import type { AgentSpec, Json } from '../types'

type Tab = 'agents' | 'semantic' | 'knowledge' | 'query'

export function AgentsData() {
  const [tab, setTab] = useState<Tab>('agents')
  const [agents, setAgents] = useState<Json | null>(null)
  const [semantic, setSemantic] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.agents(), api.semantic()])
      .then(([a, s]) => {
        setAgents(a)
        setSemantic(s)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <ErrorNote message={error} />
  if (!agents || !semantic) return <Spinner />

  return (
    <>
      <PageHeader
        eyebrow="Agents & data"
        title="Nine agents, six governed models"
        lede="Each agent has its own identity and its own tool scope. None of them can write to a core system — that door is the Secure Write Gateway, and it is not in any agent's scope."
      />
      <div className="border-b border-ink-200 mb-5">
        <Tabs
          tabs={[
            { id: 'agents' as Tab, label: 'The nine agents', count: (agents.agents as Json[]).length },
            { id: 'semantic' as Tab, label: 'Semantic layer', count: (semantic.models as Json[]).length },
            { id: 'knowledge' as Tab, label: 'Policy wording' },
            { id: 'query' as Tab, label: 'Query playground' },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>
      {tab === 'agents' && <Agents data={agents} />}
      {tab === 'semantic' && <Semantic data={semantic} />}
      {tab === 'knowledge' && <Knowledge />}
      {tab === 'query' && <QueryPlayground catalogue={semantic.query_catalogue as Json} />}
    </>
  )
}

function Agents({ data }: { data: Json }) {
  const specs = data.agents as AgentSpec[]
  const [open, setOpen] = useState<string | null>(null)
  const [detail, setDetail] = useState<Json | null>(null)

  useEffect(() => {
    if (!open) {
      setDetail(null)
      return
    }
    api.agent(open).then(setDetail).catch(() => undefined)
  }, [open])

  return (
    <div className="space-y-5">
      <Card
        title="Pipeline composition"
        subtitle="Real ADK composition — the fan-out in the architecture is the fan-out in the code"
        dense
      >
        <div className="font-mono text-[11.5px] text-ink-700 bg-ink-50 border border-ink-200 rounded p-3.5 leading-relaxed overflow-x-auto">
          {data.composition as string}
        </div>
      </Card>

      <div className="grid grid-cols-3 gap-4">
        {specs.map((s) => (
          <button
            key={s.key}
            type="button"
            onClick={() => setOpen(open === s.key ? null : s.key)}
            className={`text-left border rounded p-4 transition-colors bg-white ${
              open === s.key
                ? 'border-az-500 ring-2 ring-az-100'
                : 'border-ink-200 hover:border-ink-300'
            }`}
          >
            <div className="flex items-start gap-2.5">
              <span className="shrink-0 w-6 h-6 rounded bg-az-700 text-white text-[11px] font-semibold grid place-items-center">
                {s.ordinal}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-semibold text-ink-900">{s.title}</div>
                <Mono className="text-ink-500">{s.name}</Mono>
              </div>
            </div>
            <p className="text-[12px] text-ink-600 mt-2.5 leading-snug">{s.description}</p>
            <div className="flex items-center gap-1.5 mt-3 flex-wrap">
              <Badge tone={s.model_tier === 'capable' ? 'blue' : 'ghost'}>{s.model_tier}</Badge>
              <Badge tone="ghost" mono>
                {s.tool_count} {s.tool_count === 1 ? 'tool' : 'tools'}
              </Badge>
              <Badge tone="ghost" mono>
                {s.step_id}
              </Badge>
            </div>
          </button>
        ))}
      </div>

      {open && (
        <>
          {!detail ? (
            <Spinner />
          ) : (
            <Card
              title={`${detail.title as string} · ${detail.name as string}`}
              subtitle={detail.responsibility as string}
              right={
                <div className="flex items-center gap-2">
                  <Badge tone="ghost" mono>
                    v{detail.version as string}
                  </Badge>
                  <Badge tone="blue" mono>
                    {detail.model as string}
                  </Badge>
                </div>
              }
            >
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <div className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-500 mb-2">
                    Tool scope — the agent physically receives only these
                  </div>
                  <div className="space-y-2.5">
                    {(detail.tools as Json[]).map((t) => (
                      <div key={t.name as string} className="border-l-2 border-az-200 pl-3">
                        <div className="flex items-center gap-2">
                          <Mono className="text-az-700 font-medium">{t.name as string}</Mono>
                          <Badge tone="ghost" mono>
                            {t.risk_class as string}
                          </Badge>
                        </div>
                        <p className="text-[11.5px] text-ink-600 leading-snug mt-0.5">
                          {(t.docstring as string).split('\n')[0]}
                        </p>
                      </div>
                    ))}
                  </div>

                  <div className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-500 mb-2 mt-5">
                    What it cannot do
                  </div>
                  <ul className="space-y-1">
                    {(detail.cannot as string[]).map((c) => (
                      <li key={c} className="text-[12px] text-ink-600 flex gap-2">
                        <span className="text-stop-600">×</span>
                        {c}
                      </li>
                    ))}
                  </ul>
                </div>

                <div>
                  <div className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-500 mb-2">
                    Instruction, as the model receives it
                  </div>
                  <pre className="font-mono text-[10.5px] leading-[1.6] text-ink-700 bg-ink-50 border border-ink-200 rounded p-3 overflow-auto max-h-[420px] whitespace-pre-wrap">
                    {detail.instruction as string}
                  </pre>
                </div>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

function Semantic({ data }: { data: Json }) {
  const models = data.models as Json[]
  const ref = data.reference_data as Json

  return (
    <div className="space-y-5">
      <Card
        title="Governed semantic models"
        subtitle="An agent never sees a table and never writes SQL. It asks one of these models a named question through the Semantic Query API."
        right={<Badge tone="ok">no raw SQL exposed</Badge>}
      >
        <div className="grid grid-cols-3 gap-4">
          {models.map((m) => (
            <div key={m.name as string} className="border border-ink-200 rounded p-4">
              <Mono className="text-az-700 font-medium text-[12px]">{m.name as string}</Mono>
              <div className="flex items-center gap-1.5 mt-2">
                <Badge tone="ghost">{m.entity as string}</Badge>
                <Badge tone="ghost" mono>
                  {m.grain as string}
                </Badge>
              </div>
              <p className="text-[12px] text-ink-600 leading-snug mt-2.5">
                {m.description as string}
              </p>
              <div className="mt-3 space-y-2">
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-400">
                    Tools
                  </div>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {(m.tools as string[]).map((t) => (
                      <Mono key={t} className="text-ink-700">
                        {t}
                      </Mono>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-400">
                    Used by
                  </div>
                  <div className="text-[11.5px] text-ink-600">
                    {(m.used_by as string[]).join(', ')}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-400">
                    Measures
                  </div>
                  <div className="text-[11px] text-ink-500">
                    {(m.measures as string[]).join(' · ')}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        <Card
          title="Approved labour rates"
          subtitle="Per Austrian region, tier-1 network repairer, EUR per hour"
          dense
        >
          <Table head={['Region', 'Rate']}>
            {Object.entries(ref.labour_rates_eur as Record<string, number>).map(([r, v]) => (
              <tr key={r}>
                <Td>{r}</Td>
                <Td align="right">{eur(v)}</Td>
              </tr>
            ))}
          </Table>
        </Card>

        <Card
          title="Approved parts catalogue"
          subtitle="Part price and standard hours. Structural panels can never auto-approve."
          dense
        >
          <div className="max-h-[420px] overflow-y-auto">
            <Table head={['Panel', 'Part', 'Repair h', 'Replace h', 'Paint h', '']}>
              {Object.entries(ref.panel_catalogue as Record<string, Json>).map(([p, spec]) => (
                <tr key={p}>
                  <Td mono>{p.replace(/_/g, ' ')}</Td>
                  <Td align="right">{eur(spec.part_price_eur as number, 0)}</Td>
                  <Td align="right">{num(spec.repair_hours as number, 1)}</Td>
                  <Td align="right">{num(spec.replace_hours as number, 1)}</Td>
                  <Td align="right">{num(spec.paint_hours as number, 1)}</Td>
                  <Td>
                    {(ref.structural_panels as string[]).includes(p) ? (
                      <Badge tone="stop">structural</Badge>
                    ) : null}
                  </Td>
                </tr>
              ))}
            </Table>
          </div>
        </Card>
      </div>
    </div>
  )
}

function Knowledge() {
  const [data, setData] = useState<Json | null>(null)
  const [question, setQuestion] = useState('Is damage to my own car covered when I caused the collision?')
  const [product, setProduct] = useState('Vollkasko')
  const [result, setResult] = useState<Json | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.clauses().then(setData).catch(() => undefined)
  }, [])

  const search = async () => {
    setBusy(true)
    try {
      setResult(await api.semanticSearch(question, product || null, 'en'))
    } finally {
      setBusy(false)
    }
  }

  if (!data) return <Spinner />
  const corpus = data.corpus as Json

  return (
    <div className="space-y-5">
      <Card
        title="Grounded retrieval"
        subtitle="Filters are applied during retrieval, not afterwards. An empty result is a real answer: it means the agent abstains."
        dense
      >
        <div className="flex items-end gap-3 flex-wrap">
          <label className="flex-1 min-w-[340px] block">
            <span className="text-[11px] font-medium uppercase tracking-[0.055em] text-ink-500">
              Question
            </span>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              className="mt-1 w-full border border-ink-300 rounded px-2.5 py-1.5 text-[12.5px] focus:outline-none focus:border-az-500"
            />
          </label>
          <label className="block">
            <span className="text-[11px] font-medium uppercase tracking-[0.055em] text-ink-500">
              Product filter
            </span>
            <select
              value={product}
              onChange={(e) => setProduct(e.target.value)}
              className="mt-1 border border-ink-300 rounded px-2 py-1.5 text-[12.5px] bg-white focus:outline-none focus:border-az-500"
            >
              <option value="">no filter</option>
              <option value="Vollkasko">Vollkasko</option>
              <option value="Teilkasko">Teilkasko</option>
              <option value="Haftpflicht">Haftpflicht</option>
            </select>
          </label>
          <Button onClick={search} busy={busy}>
            Retrieve
          </Button>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-2.5">
          {[
            'Is hail damage covered and does an excess apply?',
            'Is damage to my own vehicle covered under third-party liability cover?',
            'Do I need a police report if someone was injured?',
            'What is the interest rate on my savings account?',
          ].map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setQuestion(q)}
              className="text-[11px] px-1.5 py-0.5 rounded border border-ink-200 text-ink-500 hover:border-az-400 hover:text-az-700"
            >
              {q.length > 46 ? `${q.slice(0, 46)}…` : q}
            </button>
          ))}
        </div>

        {result && (
          <div className="mt-4 pt-4 border-t border-ink-100">
            {result.abstain ? (
              <div className="border border-warn-100 bg-warn-100 rounded p-3.5">
                <div className="text-[12.5px] font-medium text-warn-700 mb-1">Abstained</div>
                <p className="text-[12px] text-warn-700 leading-snug">
                  {result.abstain_reason as string}
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {(result.citations as Json[]).map((c) => (
                  <div key={c.clause_id as string} className="border-l-2 border-az-300 pl-3">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <Mono className="text-az-700 font-medium">{c.clause_id as string}</Mono>
                      <span className="text-[12px] font-medium text-ink-800">
                        {c.title as string}
                      </span>
                      <span className="text-[10.5px] text-ink-400">
                        {c.section as string} · p.{String(c.page)} · score{' '}
                        {(c.retrieval_score as number).toFixed(2)}
                      </span>
                    </div>
                    <p className="text-[12px] text-ink-600 mt-1 leading-snug italic">
                      “{c.quote as string}”
                    </p>
                    <div className="text-[10.5px] text-ink-400 mt-1">
                      matched on {(c.matched_terms as string[]).slice(0, 8).join(', ')}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      <Card
        title="Policy wording corpus"
        subtitle={`${corpus.clause_count as number} clauses · ${corpus.chunking as string} · ${corpus.note as string}`}
        pad={false}
      >
        <div className="p-5">
          <Table head={['Clause', 'Section', 'Products', 'Title', 'Page']}>
            {(data.clauses as Json[]).map((c) => (
              <tr key={c.clause_id as string}>
                <Td mono>{c.clause_id as string}</Td>
                <Td>{c.section as string}</Td>
                <Td>
                  <div className="flex gap-1 flex-wrap">
                    {(c.products as string[]).map((p) => (
                      <Badge key={p} tone="ghost">
                        {p}
                      </Badge>
                    ))}
                  </div>
                </Td>
                <Td className="max-w-[460px]">
                  <div className="text-ink-800">{c.title as string}</div>
                  <p className="text-[11.5px] text-ink-500 leading-snug mt-0.5">
                    {c.text_en as string}
                  </p>
                </Td>
                <Td align="right">{String(c.page)}</Td>
              </tr>
            ))}
          </Table>
        </div>
      </Card>
    </div>
  )
}

function QueryPlayground({ catalogue }: { catalogue: Json }) {
  const names = Object.keys(catalogue)
  const [name, setName] = useState('get_claim_360')
  const [args, setArgs] = useState('{"reference": "AT-2026-004417"}')
  const [result, setResult] = useState<Json | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async () => {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.semanticQuery(name, JSON.parse(args)))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const spec = catalogue[name] as Json | undefined

  return (
    <div className="grid grid-cols-[380px_1fr] gap-5 items-start">
      <Card
        title="Semantic Query API"
        subtitle="The only route to business data. An unknown query name is refused, not guessed at."
        dense
      >
        <label className="block">
          <span className="text-[11px] font-medium uppercase tracking-[0.055em] text-ink-500">
            Query
          </span>
          <select
            value={name}
            onChange={(e) => {
              setName(e.target.value)
              const s = catalogue[e.target.value] as Json
              const sample: Json = {}
              for (const a of s.args as string[]) {
                sample[a] =
                  a === 'reference'
                    ? 'AT-2026-004417'
                    : a === 'policy_number'
                      ? 'AT-MOT-4417720'
                      : a === 'panel'
                        ? 'bumper_front'
                        : a === 'region'
                          ? 'Wien'
                          : a === 'severity'
                            ? 'simple'
                            : a === 'total_cost'
                              ? 1442.3
                              : a === 'template_id'
                                ? 'claim_approved'
                                : a === 'node_type'
                                  ? 'party'
                                  : a === 'node_id'
                                    ? 'PTY-AT-100904'
                                    : null
              }
              setArgs(JSON.stringify(sample, null, 2))
            }}
            className="mt-1 w-full border border-ink-300 rounded px-2 py-1.5 text-[12.5px] font-mono bg-white focus:outline-none focus:border-az-500"
          >
            {names.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        {spec && (
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            <Badge tone="blue" mono>
              {spec.model as string}
            </Badge>
            <Badge tone="ghost" mono>
              {spec.risk_class as string}
            </Badge>
          </div>
        )}
        <label className="block mt-3">
          <span className="text-[11px] font-medium uppercase tracking-[0.055em] text-ink-500">
            Arguments
          </span>
          <textarea
            value={args}
            onChange={(e) => setArgs(e.target.value)}
            rows={5}
            spellCheck={false}
            className="mt-1 w-full border border-ink-300 rounded px-2.5 py-2 text-[11.5px] font-mono focus:outline-none focus:border-az-500 resize-y"
          />
        </label>
        <Button onClick={run} busy={busy} className="mt-3 w-full">
          Execute
        </Button>
        <p className="text-[11px] text-ink-500 mt-3 leading-snug">
          Try a query name that is not in the catalogue, or a raw SQL string, to see it
          refused rather than attempted.
        </p>
      </Card>

      <div className="space-y-4">
        {error && <ErrorNote message={error} />}
        {result ? (
          <>
            <Card title="Provenance" subtitle="Every response carries its own lineage" dense>
              <KeyValueGrid cols={4}>
                {Object.entries(result.provenance as Json).map(([k, v]) => (
                  <Field key={k} label={k.replace(/_/g, ' ')} mono>
                    {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                  </Field>
                ))}
              </KeyValueGrid>
            </Card>
            <Card title="Data" dense>
              <JsonBlock value={result.data} maxHeight={520} />
            </Card>
          </>
        ) : (
          !error && <Empty>Run a query to see the response and its provenance.</Empty>
        )}
      </div>
    </div>
  )
}
