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
