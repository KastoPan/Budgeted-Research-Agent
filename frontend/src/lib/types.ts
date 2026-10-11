export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "completed_with_limitations"
  | "budget_exhausted"
  | "insufficient_evidence"
  | "cancelled"
  | "failed";

export type PolicyName = "fixed" | "adaptive";
export type PolicyProfile = "standard" | "smoke";

export interface ResearchBudget {
  max_tokens: number;
  max_searches: number;
  max_page_fetches: number;
  max_elapsed_seconds: number;
  max_cost_usd?: number | null;
}

export interface ResearchRequest {
  question: string;
  budget: ResearchBudget;
}

export interface CreateRunInput {
  question: string;
  policy: PolicyName;
  profile: PolicyProfile;
  budget: ResearchBudget;
}

export interface StoredRun {
  run_id: string;
  question: string;
  policy: "fixed_depth" | "adaptive_budget";
  profile: PolicyProfile;
  status: RunStatus;
  request: ResearchRequest;
  stop_reason: string | null;
  artifact_directory: string | null;
  total_tokens: number;
  total_cost_usd: number;
  search_count: number;
  page_fetch_count: number;
  elapsed_seconds: number;
  action_count: number;
  created_at: string;
  updated_at: string;
}

export type ActionStatus = "started" | "completed" | "failed" | "rejected";
export type ActionType =
  | "plan"
  | "search"
  | "fetch"
  | "extract_evidence"
  | "write_report";

export interface ActionRecord {
  sequence: number;
  action_id: string;
  action_type: ActionType;
  policy: string;
  target: string | null;
  reason: string;
  status: ActionStatus;
  occurred_at: string;
  estimated_resources: Record<string, number>;
  actual_resources: Record<string, number>;
  decision_context: Record<string, string | number | boolean>;
  error: string | null;
}

export type SourceQualityTier =
  | "primary"
  | "authoritative"
  | "documentation"
  | "community"
  | "unknown";

export interface SourceQuality {
  score: number;
  tier: SourceQualityTier;
  reasons: string[];
}

export interface EvidenceItem {
  id: string;
  subquestion_id: string;
  claim: string;
  support_span: string;
  source_id: string;
  source_url: string;
  source_title: string;
  retrieved_at: string;
  source_quality: SourceQuality;
}

export interface ReportAssertion {
  text: string;
  evidence_ids: string[];
}

export interface ReportSection {
  subquestion_id: string;
  heading: string;
  assertions: ReportAssertion[];
}

export interface ResearchReport {
  title: string;
  sections: ReportSection[];
  markdown: string;
  citation_ids: string[];
  rejected_assertion_count: number;
  omitted_assertion_count: number;
  rejection_reasons: string[];
}
