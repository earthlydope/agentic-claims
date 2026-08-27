export type Json = Record<string, any>

export interface Claim {
  reference: string
  status: string
  stage: string
  decision: string | null
  settlement_amount_eur: number
  severity: string | null
  structural_damage: boolean
  injury_reported: boolean
  fraud_score: number
  evidence_completeness: number
  straight_through: boolean
  human_touches: number
  channel: string
  language: string
  incident_type: string | null
  incident_region: string | null
  incident_city: string | null
  incident_date: string | null
  reported_at: string | null
  sla_due_at: string | null
  assigned_queue: string | null
  assigned_to: string | null
  scenario_key: string | null
  scenario: Scenario | null
  is_live_demo: boolean
  fnol_text?: string
  incident_location?: string
  collision_type?: string
  third_party_involved?: boolean
  police_report_ref?: string | null
  policyholder: { party_id: string; name: string; city: string; region: string; language: string; segment: string; customer_since: string } | null
  vehicle: { vin: string; plate: string; make: string; model: string; year: number; market_value_eur: number } | null
  policy: { policy_number: string; product: string; product_label_en: string; status: string; excess_eur: number; annual_premium_eur: number } | null
  open_task: { task_id: string; queue: string; reason: string; authority_required: string; proposed_amount_eur: number } | null
}

export interface Scenario {
  key: string
  title: string
  party_id: string
  headline: string
  expect: string
  demonstrates: string[]
}

export interface TraceEvent {
  seq: number
  run_id: string
  claim_reference: string
  kind: string
  step_id: string
  step_no: number | null
  step_title: string | null
  lane: string | null
  pillar: number | null
  agent: string | null
  status: string
  detail: string
  data: Json
  elapsed_ms: number
  at: string
}

export interface Step {
  no: number
  id: string
  lane: string
  title: string
  pillar: number | null
}

export interface AgentSpec {
  key: string
  name: string
  ordinal: number
  title: string
  description: string
  responsibility: string
  tool_scope: string[]
  cannot: string[]
  model_tier: string
  model: string
  version: string
  step_id: string
  tool_count: number
}

export interface ReviewTask {
  task_id: string
  claim_reference: string
  queue: string
  reason: string
  authority_required: string
  authority_limit_eur: number
  priority: number
  status: string
  assigned_to: string | null
  proposed_decision: string | null
  proposed_amount_eur: number
  age_minutes: number
  sla_due_at: string | null
  sla_breached: boolean
}

export interface Staff {
  user_id: string
  name: string
  role: string
  role_label: string
  authority_limit_eur: number
  queues: string[]
  location: string
  note: string
}


export interface PersonaFeature {
  key: string
  label: string
  hint: string
  icon: string
  stages: string[]
}

export interface CoworkerTool {
  name: string
  label: string
  description: string
  risk_class: string
}

export interface Coworker {
  name: string
  tagline: string
  remit: string
  tools: CoworkerTool[]
  starters: string[]
  cannot: string[]
}

export interface Persona {
  key: string
  user_id: string
  name: string
  initials: string
  role_label: string
  role_de: string
  kind: 'customer' | 'staff'
  location: string
  authority_limit_eur: number
  queues: string[]
  remit: string
  measured_on: string[]
  party_id: string | null
  accent: string
  /** Which 3D illustration represents this role. */
  avatar: string
  features: PersonaFeature[]
  coworker: Coworker
}

export interface Stage {
  no: number
  id: string
  title: string
  lane: string
  owner: string
  pillar: number | null
  agent: string | null
  summary: string
  exceptions: string[]
}

export interface StatusMeta {
  key: string
  label: string
  /** The Austrian wording, sent alongside the English rather than translated in the UI. */
  label_de?: string
  stage: string | null
  tone: string
  terminal: boolean
  description: string
  description_de?: string
  [field: string]: unknown
}

export interface WorkTask {
  task_id: string
  claim_reference: string
  queue: string
  reason: string
  reason_detail: string
  proposed_decision: string | null
  proposed_amount_eur: number
  authority_required: string
  within_my_authority: boolean
  priority: number
  sla_due_at: string | null
  sla_breached: boolean
  age_minutes: number
  policyholder: string
  severity: string | null
  structural: boolean
  injury: boolean
  status: StatusMeta
}

export interface CoworkerReply {
  turn_id: string
  conversation_id: string
  blocked: boolean
  coworker: string
  answer: string
  references?: string[]
  suggested_actions?: string[]
  needs_a_person?: boolean
  tools_used?: string[]
  model?: string
  runtime?: string
  latency_ms?: number
  firewall?: Json
  outbound_guard?: Json | null
}
